Below is a more implementation-oriented developer README version of the spec.

# Overlap Annotation App — Developer README

## Goal

Build a small web application for annotating overlapping speech in audio segments. The system must support annotator onboarding, calibration, production annotation, user progress tracking, and a lightweight queue-based repeated annotation workflow.

The MVP intentionally keeps the routing logic simple. Only a coarse binary label is used for routing:

* `negative` = no useful overlap
* `positive` = overlap exists, whether it is localizable or not

Detailed span annotations, intelligibility labels, and text are stored, but they do not affect routing, conflict detection, or sample closure in the MVP.

## Product behavior

The UI presents one audio segment at a time. The annotator chooses one of three segment-level options:

1. No useful overlap
2. Overlap exists, but cannot be localized reliably
3. Overlap exists and can be localized

If the annotator selects the third option, the UI must reveal span annotation controls. Each span has an intelligibility level and optional text.

Routing simplifies these three options into two labels:

* option 1 maps to `negative`
* options 2 and 3 map to `positive`

This means conflict detection is also binary. A conflict exists only if accepted annotations disagree on `negative` versus `positive`.

## User flow

When a user logs in, the application must restore progress and continue from the correct stage.

The full flow is:

1. First login shows the annotation rules document.
2. The user completes 5 tutorial examples with immediate feedback after each example.
3. The user completes 5 calibration examples and sees the correct answers only at the end of the calibration block.
4. The user then enters production annotation mode and continues receiving production tasks without a fixed per-user limit.

The application must remember whether the user has not started onboarding yet, is currently in tutorial, is currently in calibration, has completed onboarding, or is already working on production tasks.

## Backend overview

The backend is responsible for four things:

first, authenticating annotators through pre-generated login codes;

second, deciding which sample to return next depending on onboarding stage or production queue state;

third, accepting submits and updating sample state;

fourth, preserving user progress and current task state.

The MVP does not use hard locking across all users. Instead, it uses best-effort assignment and treats submit as the source of truth. To reduce accidental double-assignment to the same user, each user has a `current_sample_id`. If this field is already set, the backend returns that same sample again instead of assigning a new one.

This avoids the most obvious double-tab issue for the same user without introducing reservation logic or lock expiration.

## Frontend overview

The frontend should have a single main annotation page and a lightweight login page.

After login, the frontend should route the user according to backend state. It should not infer state itself.

The main annotation page must support three modes:

tutorial mode, where each submit is followed by immediate feedback;

calibration mode, where submits are collected until the end of the block and only then the correct answers are shown;

production mode, where no gold feedback is shown.

When the user selects the third segment-level option, the page must reveal span editing controls. Each span must support start time, end time, intelligibility, and optional text.

The submit button should be disabled immediately after click until the request resolves, to reduce accidental repeated submits.

## Database schema

The MVP uses three tables: `users`, `samples`, and `annotations`.

### users

This table stores annotator identity and progress.

Recommended fields:

* `id`
* `login_code`
* `display_name`
* `created_at`
* `current_sample_id`
* `stage`
* `tutorial_index`
* `calibration_index`
* `onboarding_completed_at`

The `stage` field should represent the current phase, for example `rules`, `tutorial`, `calibration`, or `production`.

`tutorial_index` and `calibration_index` should point to the next item to show within those phases.

`current_sample_id` stores the currently active sample for that user, if any.

### samples

This table stores both sample content and aggregated state.

Recommended fields:

* `id`
* `sample_type`
* `audio_path`
* `recognized_text`
* `golden_annotation`
* `queue_type`
* `is_closed`
* `accepted_annotation_count`
* `created_at`
* `updated_at`

`sample_type` must distinguish at least `tutorial`, `calibration`, and `production`.

`golden_annotation` is used for tutorial and calibration samples. For production samples it may be null.

`queue_type` applies only to production samples and should support at least `unseen`, `negative`, `positive`, and `conflict`.

`accepted_annotation_count` counts only accepted annotations.

### annotations

This table stores meaningful submissions that the server keeps.

Recommended fields:

* `id`
* `sample_id`
* `user_id`
* `label`
* `annotation_data`
* `created_at`
* `status`

`label` is the coarse routing label and can only be `negative` or `positive`.

`annotation_data` is JSON and should store the full detailed annotation payload, including the exact UI choice, spans, intelligibility levels, and optional text.

`status` should support:

* `accepted`
* `overdone`

The table must enforce uniqueness on `(sample_id, user_id)`.

That uniqueness constraint is important. It guarantees that one user cannot contribute more than one stored annotation to the same sample.

## Annotation payload format

The backend should treat `annotation_data` as the full detailed output of the UI.

A reasonable shape is:

```json
{
  "ui_choice": "positive_localizable",
  "spans": [
    {
      "start": 1.42,
      "end": 2.87,
      "intelligibility": "partial",
      "text": "well maybe [inaudible]"
    }
  ]
}
```

The routing label derived from that payload would still just be `positive`.

For a negative example, the payload can be simpler:

```json
{
  "ui_choice": "negative",
  "spans": []
}
```

The backend should not derive routing from spans or text. It should derive routing only from the segment-level UI choice.

## Business rules

A production sample starts in the `unseen` queue.

After a submit, routing works as follows.

If the accepted annotation is `negative`, the sample is added to the `negative` queue with probability `0.1`.

If the accepted annotation is `positive`, the sample is always added to the `positive` queue.

If accepted annotations disagree on the coarse label, the sample is moved to the `conflict` queue.

A sample closes as soon as one of these becomes true:

* it has two accepted annotations with the same coarse label
* it has three accepted annotations total

Closed samples must not remain in any queue.

A conflict means only this: accepted labels disagree on `negative` versus `positive`.

Nothing else counts as conflict in the MVP.

## Queue selection

Queue selection applies only to production samples.

The backend should always follow this order:

If the `conflict` queue is non-empty, select from `conflict` first.

If `conflict` is empty, choose among non-empty queues `positive`, `unseen`, and `negative` using the following weights:

* `positive = 0.45`
* `unseen = 0.45`
* `negative = 0.10`

These weights must be normalized over non-empty queues only.

The backend must also filter out samples already annotated by the current user.

## Task assignment rules

When the frontend asks for the next task, the backend should first inspect the user state.

If the user is still in tutorial, return the tutorial sample at `tutorial_index`.

If the user is in calibration, return the calibration sample at `calibration_index`.

If the user is in production, first check `current_sample_id`.

If `current_sample_id` is set, return that same sample again. This prevents one user from silently accumulating multiple active tasks in multiple tabs.

If `current_sample_id` is null, assign a new production sample according to queue rules and then store its id in `current_sample_id`.

The backend should never assign a production sample to a user if there is already an annotation row for the same `(sample_id, user_id)`.

## Submit handling

Submit handling is the most important backend flow.

The backend should process a submit in this order.

First, check whether an annotation already exists for `(sample_id, user_id)`. If it does, reject the submit as duplicate and clear `current_sample_id`.

Second, if no such row exists, check whether the sample is already closed or has already reached the accepted annotation limit. If yes, store the annotation as `overdone` and clear `current_sample_id`.

Third, if the sample is still active, store the annotation as `accepted`.

After storing an accepted annotation, recompute the sample state. If the sample now has two accepted annotations with the same label, close it. If it now has three accepted annotations, close it. Otherwise, assign the sample to the next queue according to the routing rules.

After any submit outcome, including duplicate rejection and overdone, clear `current_sample_id`.

## Overdone semantics

An annotation is `overdone` when it was submitted after the sample had already been closed or after the sample had already reached the accepted annotation limit.

This can happen naturally in the MVP because assignment is best-effort and multiple users may sometimes be working on the same sample concurrently.

Overdone annotations must be saved, but they must not affect routing or accepted annotation count.

## Duplicate semantics

A duplicate means the same user attempted to submit again for the same sample.

Because `(sample_id, user_id)` is unique in `annotations`, only one stored annotation from that user can exist for that sample.

A duplicate submit should be rejected and should not create a second annotation row.

## Onboarding logic

Tutorial and calibration should use `sample_type` and `golden_annotation`.

Tutorial submits should be stored as normal annotations if you want to preserve user behavior, but they should not affect production queues.

Calibration submits should also remain isolated from production routing.

The backend should advance `tutorial_index` or `calibration_index` after each successful submit in those stages.

When tutorial is completed, move the user to calibration.

When calibration is completed, set `onboarding_completed_at`, move the user to `production`, and clear the calibration index.

## Admin mode

The application should include a minimal admin mode for internal use.

The admin mode does not need to be a full-featured moderation panel. It only needs to support a few core workflows:

* creating and editing annotators in the `users` table, including generating and assigning login codes;
* creating and editing tutorial and calibration samples;
* creating and editing `golden_annotation` for tutorial and calibration samples;
* inspecting production samples together with all submitted annotations for debugging and manual review.

For creating golden annotations, admin mode should reuse the same annotation UI as the annotators whenever possible. The admin should be able to open a sample, annotate it with the standard interface, and save the result as `golden_annotation` instead of a normal user annotation.

Admin mode can be protected in a very simple way for the MVP, for example by using a dedicated admin account, an allowlist, or a simple `is_admin` flag on the user.

## Raw annotation pool

The raw production candidate pool is stored in `annotation_pool.tsv`.

This file is the source pool from which production samples are loaded into the application.

The file currently has the following header:

```text
start_overlap	end_overlap	Duration	origin	overlap_dur	rms_global	p80	prediction	is_bad	audio_path
```

The `audio_path` column points to the audio file used by the annotation UI. The remaining columns are metadata from the automatic overlap mining pipeline and can be preserved for reference, filtering, import logic, or future analysis.

For the MVP, the application should be able to import samples from `annotation_pool.tsv` into the `samples` table and initialize them as production samples in the `unseen` queue.



## Suggested API shape

A minimal API can look like this.

`POST /login`

Takes a login code, finds the user, creates a session, and returns current stage information.

`GET /me`

Returns the logged-in user profile and current progress state.

`GET /task/current`

Returns the current task for the user. Depending on stage, this may be tutorial, calibration, or production.

`POST /task/submit`

Takes the current sample id and annotation payload. The backend validates, saves, updates progress, updates queues if needed, and returns the next UI state.

`GET /calibration/results`

Returns correct answers after calibration is completed.

You do not need many endpoints for the MVP. It is fine if `/task/current` and `/task/submit` carry most of the logic.

## Suggested frontend screens

A minimal frontend can consist of:

a login screen where the user enters their login code;

a rules screen shown only before onboarding starts;

a single annotation screen reused for tutorial, calibration, and production;

an optional calibration results screen shown once after calibration;

a minimal progress widget showing current stage and item number.

The annotation screen should not need separate pages per mode. It can render mode-specific behavior based on backend state.

## Suggested validations

The frontend should require a segment-level choice before submit.

If the user selects the localizable positive option, the UI should allow span creation. Whether at least one span is required is a product choice. For the MVP, it is acceptable to allow zero spans and still save the annotation, because routing does not depend on span existence.

The backend should always validate the coarse label independently of the detailed payload.

## Suggested implementation priorities

The fastest sensible implementation order is:

First build login, session handling, and user progress persistence.

Then implement sample loading and the single annotation screen.

Then implement tutorial and calibration flow with golden annotations.

Then implement production queue assignment and submit logic.

Finally add convenience features like progress counters, admin views, and better review tooling.

## Non-goals for the MVP

The MVP does not need:

hard global reservation locks across all users;

real-time queue balancing;

span agreement logic;

text agreement logic;

advanced adjudication;

annotator quality scoring;

complex analytics dashboards.

Those can all be added later once real annotation data exists.

## Summary

The core design principle is simple:

assignment is best-effort, submit is the source of truth.

A user should have only one active current sample at a time. Routing uses only a binary `negative` versus `positive` label. Detailed span information is stored but ignored for queue logic. Closed samples are removed from active queues. Duplicate submits from the same user are rejected. Extra late submissions from other users are stored as `overdone` and do not affect routing.

If you want, I can turn this into an even more concrete engineering handoff with example SQL schemas and backend pseudocode for `get_current_task()` and `submit_annotation()`.
