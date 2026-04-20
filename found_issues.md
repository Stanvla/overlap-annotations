# Found Issues

Review date: 2026-04-20

This file summarizes the currently relevant issue found during a review of the project documentation, backend code, tests, and operational scripts.

Update after project-owner clarification:

- only finding 1 remains relevant
- finding 2 is not treated as a current issue for this MVP, because annotators are assumed to use only the web client and the backend intentionally uses best-effort assignment rather than strict enforcement
- finding 3 is not a bug; the implemented logic is intentional and the documentation should be understood accordingly
- finding 4 is an accepted MVP/admin workflow compromise and is not treated as a current issue

## Scope of review

- Read the main specification in [technical_documentation.md](technical_documentation.md)
- Read the extension notes in [technical_documentation_extension.md](technical_documentation_extension.md)
- Read the project history in [project_log.md](project_log.md)
- Reviewed backend code in [webapp/app.py](webapp/app.py), [webapp/db.py](webapp/db.py), [webapp/import_data.py](webapp/import_data.py), and [webapp/run.py](webapp/run.py)
- Reviewed tests in [tests/test_app.py](tests/test_app.py)
- Reviewed operational files [deploy.sh](deploy.sh), [backup.sh](backup.sh), and [deployment.md](deployment.md)

## Overall status

- The automated test suite passed: `63 passed`
- Only one issue remains relevant: a latent backend validation gap in the onboarding submit flow
- No code changes were made during this review

## Relevant finding

### 1. Low: Tutorial and calibration submit paths do not enforce the expected onboarding sample on the backend

Relevant code:

- [webapp/app.py](webapp/app.py#L309)
- [webapp/app.py](webapp/app.py#L316)
- [webapp/app.py](webapp/app.py#L351)
- [static/index.html](static/index.html#L782)
- [static/index.html](static/index.html#L1072)

Problem:

The submit handler loads whatever sample matches the incoming `sample_id` before branching by user stage, but the tutorial and calibration branches do not verify either of these two invariants:

- the submitted sample must belong to the correct stage (`tutorial` or `calibration`)
- the submitted sample must be the exact sample the user is currently supposed to be annotating according to `tutorial_index` or `calibration_index`

In other words, the code that serves onboarding tasks is index-driven, but the code that accepts onboarding submissions is `sample_id`-driven.

Short version:

- the backend decides what the user should annotate next by looking at the user state
- but when the answer comes back, the backend does not verify that the answer belongs to that expected sample
- so "what the user was supposed to annotate" and "what the backend accepts as completed" can become different things

Important clarification:

- with the current web client, normal usage does submit the correct sample ID
- the frontend stores the loaded task in `currentTask` and submits `currentTask.sample.id`
- so if the UI loaded sample `11`, the browser will normally submit `11`
- this issue is therefore not a demonstrated current UI bug in ordinary usage

What remains relevant is the backend invariant gap:

- the server relies on the frontend to preserve onboarding correctness
- the server does not enforce that correctness itself

Expected flow:

- `/api/task/current` resolves the current onboarding sample from the user state
- tutorial users should only be able to submit the tutorial sample at `tutorial_index`
- calibration users should only be able to submit the calibration sample at `calibration_index`

Actual flow:

- `/api/task/submit` accepts any existing sample ID
- once the user is in the tutorial branch, the code only checks for duplicates by `(sample_id, user_id)`
- once the user is in the calibration branch, the code does the same
- neither branch checks sample type or whether the sample matches the user’s expected onboarding item

Why this is still relevant:

This is no longer best described as a high-severity practical bug. It is better described as a latent backend consistency gap.

The server has one implicit rule:

- if a user completes tutorial item `n`, then the stored annotation should belong to tutorial item `n`

Right now that rule is not enforced by the submit handler.

So if the frontend ever sends the wrong `sample_id` because of a stale state bug, a rendering bug, a race during navigation, or a future UI refactor, the backend will silently accept the wrong sample as if the correct onboarding item had been completed.

That means:

- a tutorial user can submit a production sample
- a calibration user can submit a tutorial or production sample
- the handler only checks for duplicate submission by the same user, not stage correctness or expected sample identity

Why this matters:

- current practical impact is low as long as the web client is the only client and continues to behave as it does now
- the backend still lacks an internal correctness check for onboarding progress
- if the client ever submits the wrong sample ID, the server will accept it without detecting that onboarding state and submitted sample do not match
- in that case, a wrong-stage annotation can be stored as `accepted`
- and when this happens through the tutorial/calibration branch, production queue state is not recomputed, so the `annotations` table can diverge from the `samples` aggregate fields such as `accepted_annotation_count`, `queue_type`, and `is_closed`

Potential failure mode:

If a tutorial user submits a production sample through the tutorial branch:

- the annotation row is inserted as `accepted`
- `tutorial_index` is incremented
- the user may advance to calibration
- the production sample does not go through the production routing logic
- `accepted_annotation_count` on the production sample is not incremented
- `queue_type` is not updated
- `is_closed` is not recomputed

So a single wrong request can both corrupt production sample bookkeeping and incorrectly advance onboarding state.

## Step-by-step example

Example setup:

- user stage = `tutorial`
- `tutorial_index = 0`
- the expected tutorial sample is tutorial sample `T1`, for example `sample_id = 11`
- there also exists a production sample `P7`, for example `sample_id = 700`

What should happen:

1. The user asks for the current task.
2. The backend resolves tutorial item `0` and returns sample `11`.
3. The user submits an annotation for sample `11`.
4. The backend stores that tutorial annotation and increments `tutorial_index`.

What the backend would also allow if it received the wrong sample ID:

1. The user is still in tutorial stage.
2. A submit arrives with `sample_id = 700` instead of `11`.
3. The backend sees `user["stage"] == "tutorial"`, so it enters the tutorial branch.
4. It checks only whether this user already annotated sample `700`.
5. If not, it inserts an `accepted` annotation row for sample `700`.
6. It increments `tutorial_index` anyway.
7. The user may advance to calibration even though tutorial sample `11` was never actually completed.

That is the core gap: the backend marks the onboarding step as completed without verifying that the submitted answer belongs to the onboarding sample that step refers to.

Again, this is not what the current web client normally does. This is what the backend would accept if the client ever sent the wrong ID.

## Why the data could become inconsistent

The inconsistency comes from using the wrong branch for the submitted sample.

Tutorial branch behavior:

- insert annotation row
- increment tutorial progress
- return tutorial feedback

Production branch behavior:

- insert annotation row
- update `accepted_annotation_count`
- recompute `queue_type`
- possibly set `is_closed`
- clear current production assignment

If a production sample is submitted while the user is in tutorial, the tutorial branch runs instead of the production branch.

So the database would end up in a mixed state:

- the `annotations` table says the production sample received an accepted annotation
- but the `samples` table still has old aggregate values for that same production sample

Concrete example:

- production sample `700` initially has `accepted_annotation_count = 0`, `queue_type = unseen`, `is_closed = 0`
- tutorial user submits sample `700`
- a new accepted annotation row is inserted for sample `700`
- but `accepted_annotation_count` stays `0`
- `queue_type` stays `unseen`
- `is_closed` is not recomputed

So one part of the database says "this sample has been annotated" and another part still says "this sample has zero accepted annotations and has never been routed".

## Another hypothetical example with calibration

Example setup:

- user stage = `calibration`
- `calibration_index = 2`
- expected calibration sample is `C3`, for example `sample_id = 205`
- submitted sample is a tutorial sample `T1`, for example `sample_id = 11`

If such a wrong submit reached the backend, the result would be:

- the calibration branch accepts the submit
- the annotation for tutorial sample `11` is inserted as accepted
- `calibration_index` is incremented
- the user moves closer to production

So again, the backend would treat "answered some sample" as equivalent to "completed the expected calibration sample", which is not logically correct.

## Why this is different from finding 2

Finding 2 was about whether production users must be forced to submit only their currently assigned production task.

You clarified that in this MVP the answer is no, because the web client is the only intended client and the assignment model is best-effort.

Finding 1 is different.

Here the issue is not strictness of task assignment. The issue is that the backend would be willing to record completion of onboarding step `n` while storing an annotation for a completely different sample. That breaks an internal consistency rule of the onboarding flow itself, even if the current frontend happens not to trigger it.

## What the fix conceptually looks like

When the user is in tutorial:

- compute the expected tutorial sample from `tutorial_index`
- reject the submit unless `sample_id` equals that sample’s ID

When the user is in calibration:

- compute the expected calibration sample from `calibration_index`
- reject the submit unless `sample_id` equals that sample’s ID

This keeps task selection and submit validation tied to the same source of truth.

What was reproduced during review:

- the backend accepted a direct API submit where a tutorial-stage user posted a production sample ID
- the server returned success
- the user advanced to calibration
- an annotation row was created for the production sample
- the production sample state itself was not updated accordingly

Important limitation of that reproduction:

- this was a backend/API reproduction
- it was not reproduced through the normal browser flow of the current web client
- the current web client submits `currentTask.sample.id`, so in ordinary use it submits the sample that was actually loaded

Root cause:

The onboarding submit branches trust the provided `sample_id` instead of resolving the expected current onboarding sample from the user state and verifying that the two match.

## Clarified non-issues

### 2. Production submit without strict assignment enforcement

This is not treated as a current issue for this MVP.

Reason:

- annotators are assumed to use only the web client
- the project intentionally uses a best-effort workflow rather than strict task-lock enforcement
- under normal web-client usage, the frontend fetches the current task and submits that task, so this is not currently a practical problem

Conclusion:

This would become relevant only if the project later introduces multiple clients, stricter workflow guarantees, or stronger server-side enforcement requirements.

### 3. Negative-routing behavior

This is not treated as a bug.

Clarified intended behavior:

- most negative samples should close immediately
- only a small portion should be sent to the negative queue as a sanity check
- the operational goal is to focus repeated annotation effort on likely positives rather than to double-check everything

Conclusion:

The implementation is considered correct. The only follow-up implied by the earlier review is that documentation should remain aligned with that intended behavior.

### 4. Onboarding picker using manually selected admin-produced examples

This is not treated as a current issue.

Reason:

- this is an accepted MVP compromise
- onboarding and calibration content was intentionally curated by the admin based on manual annotation choices
- the looser picker logic reflects that practical workflow rather than a fully automated gold-generation pipeline

## Why the test suite still passed

The existing tests cover a lot of important behavior well:

- authentication and session handling
- stage progression across rules, tutorial, calibration, and production
- normal queue behavior
- admin CRUD flows
- export behavior
- database initialization and pragmas

The missing coverage is mainly around onboarding integrity cases:

- wrong-stage sample submission

That gap explains why the suite can pass while the remaining backend validation gap still exists.

## Suggested improvements

1. In `/api/task/submit`, enforce stage-specific sample validation.
2. For tutorial and calibration submits, resolve the expected current onboarding sample from user state and require the submitted `sample_id` to match it.
3. Add regression tests for wrong-stage submit and wrong-onboarding-sample submit.

## Verification notes

The following were verified during review:

- the project’s tests run successfully in the configured `overlap_annotations` conda environment
- `pytest` was not initially installed in that environment and was installed before running the suite
- the backend validation gap was reproduced directly with the Flask test client
- the current frontend submit path was checked and it normally submits `currentTask.sample.id`