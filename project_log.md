# Project Log — Overlap Annotation Web App

Chronological log of all changes made to the application.

---

## 2026-04-19 — Initial Setup

### Project scaffolding
- Created initial project structure with `pyproject.toml`, `annotation_pool.tsv`, audio files in `selected_audios/`
- Set up Python package configuration (requires Python 3.10+, Flask 3.0+, pandas, numpy, etc.)

### Web application (v1)
- Built Flask backend (`webapp/app.py`) with SQLite database (`webapp/db.py`)
- Database schema: 3 tables — `users`, `samples`, `annotations` with indexes and WAL journal mode
- Implemented authentication via login codes (cookie-signed sessions)
- Created annotation workflow: tutorial → calibration → production pipeline
- Implemented production queue system with weighted selection (positive 45%, unseen 45%, negative 10%, conflict priority)
- Built sample lifecycle: annotation counting, automatic closure (2 agreeing or 3 total), conflict detection
- Created import script (`webapp/import_data.py`) to load samples from `annotation_pool.tsv`
- Built single-page frontend (`static/index.html`) with login, annotation, and admin screens

### Package configuration fix
- Fixed `pyproject.toml` flat-layout error by adding `[tool.setuptools.packages.find]` with `include = ["webapp*"]`

### Waveform visualization
- Replaced plain `<audio>` element with WaveSurfer.js v7 interactive waveform
- Added drag-to-select span creation on the waveform (for "positive, localizable" annotations)
- Color-coded span regions cycling through 5 colors (blue, red, green, orange, purple)

### Playback controls
- Added speed selector: 0.5×, 0.75×, 1×, 1.25×, 1.5×, 2×
- Speed persists across samples within the same session
- Added per-span play button (▶) with auto-stop at span end
- Added per-span loop toggle (🔁) for repeated listening
- Real-time time display in `M:SS.mm` format

---

## 2026-04-20 — Feature Development

### Annotation rules integration
- Created `GET /api/rules` endpoint serving `annotatori_pravidla_overlap.md`
- Added rules acknowledgement workflow (users must acknowledge before starting tutorial)
- Built client-side Markdown-to-HTML converter for rules rendering
- Added **ℹ️ Pravidla** button in header — opens scrollable rules modal anytime
- Rules content cached after first fetch

### Golden annotation modal for admin
- Added full waveform-based modal for creating "positive, localizable" golden annotations
- Modal includes: drag-to-create spans, intelligibility dropdown, transcript textarea, play/delete per span
- Added quick-set buttons for "Negative" and "Positive (not localizable)" golden annotations
- Golden annotation details (span times, intelligibility, text) displayed in admin sample cards

### Tutorial/calibration sample management
- Added `POST /api/admin/samples/pick-for-onboarding` — picks already-annotated production samples and creates tutorial/calibration copies with auto-derived golden annotations
- Added `DELETE /api/admin/samples/{id}` — removes tutorial/calibration samples and their annotations
- Admin can select number of samples to pick via prompt

### Golden annotation display fix
- Fixed `goldenSummary()` to show full span details (times, intelligibility, transcript) instead of just span count
- Fixed field name mismatch: spans use `text` field, not `transcribed_text`

### User reset fix
- Fixed: resetting a user to an onboarding stage now **deletes** their old tutorial/calibration annotations
- Previously, reset users hit "Already submitted" errors because old annotations still existed

### Tutorial feedback with interactive waveforms
- Golden spans rendered as green regions on the existing waveform during tutorial feedback
- Added play buttons per golden span in tutorial feedback (▶ Span 1 (1.2s–3.4s))
- Clicking plays that exact region and auto-stops

### Calibration results with waveforms
- Replaced plain `<audio>` tags with full WaveSurfer.js waveform instances per calibration result
- Golden span regions shown as green highlights on each waveform
- Play buttons per golden span with auto-stop
- Waveform instances properly cleaned up when navigating away

### Annotation export system
- Added `GET /api/admin/export?format={tsv|json}` endpoint with optional `&sample_type=` filter
- Added **⇓ Export TSV** and **⇓ Export JSON** buttons in admin panel header
- TSV columns: annotation_id, sample_id, sample_type, audio_path, recognized_text, user_id, display_name, label, ui_choice, span_count, spans_json, status, is_closed, accepted_annotation_count, queue_type, created_at

### Auto-export after each production annotation
- `auto_export()` function runs after every accepted production submission
- Writes `annotations_export.tsv` and `annotations_export.json` to project root (configurable via `EXPORT_DIR`)
- Best-effort: failures don't break annotation flow

### Git auto-commit of exports
- After writing export files, auto-runs `git add` + `git commit` with message "auto: update annotation exports"
- Silently skipped if git not available or no changes

### Backup script (`backup.sh`)
- Safe SQLite backup using `.backup` command (handles WAL correctly)
- Saves to `backups/annotations_YYYYMMDD_HHMMSS.db`
- Keeps last 10 backups, auto-deletes older ones
- Can be automated via cron (e.g., every 6 hours)

### Deployment script (`deploy.sh`)
- Creates Python venv, installs dependencies + gunicorn
- Generates and persists `SECRET_KEY` to `.secret_key` (chmod 600)
- Starts gunicorn with configurable `PORT`, `HOST`, `WORKERS` env vars
- Checks for Python 3.10+, warns if `selected_audios/` missing

### Documentation
- Created `deployment.md` — step-by-step deployment guide (server setup, systemd, nginx, HTTPS, backups)
- Created `technical_documentation_extension.md` — all features beyond the original spec

### Calibration analytics notebook
- Created `notebooks/calibration_success_rate.ipynb` for quick calibration-quality analysis from the SQLite database
- Notebook loads accepted calibration annotations, joins them with calibration samples and golden annotations, and computes per-user success metrics
- Added two visual success-rate views: coarse label success (`negative` vs `positive`) and exact UI choice success (`negative`, `positive_not_localizable`, `positive_localizable`)
- Added a mismatch table to inspect which calibration items each annotator answered incorrectly

### Production annotation counter
- Added `production_annotation_count` to user data (counts only accepted production annotations)
- Displayed next to user's name in header as "(X annotated)", updates live after each submission
- Added "Annotated" column in admin user table

### Progress bar fix
- Fixed: tutorial/calibration progress bar now shows actual sample count from database
- Previously used hardcoded `TUTORIAL_COUNT = 5` / `CALIBRATION_COUNT = 5` constants
- Now queries `SELECT COUNT(*) FROM samples WHERE sample_type = ?` for accurate totals
- Removed unused `TUTORIAL_COUNT` and `CALIBRATION_COUNT` constants

### Admin queue overview
- Added `GET /api/admin/queues` endpoint — returns counts for all production queues (unseen, positive, negative, conflict, closed) plus total
- Optional `?queue=` parameter returns samples in that queue with all accepted annotations (user ID, name, label, full annotation data with spans)
- Redesigned Production tab in admin panel with clickable queue cards showing live counts
- Color-coded cards: unseen (amber), positive (green), negative (gray), conflict (red), closed (indigo)
- Clicking a queue drills down to show all samples with inline annotation details per sample
- Each annotation shows: annotator name, user ID, coarse label, detailed UI choice, span details (times, intelligibility, text), timestamp

### Interactive waveforms in admin queue drill-down
- Replaced plain `<audio>` tags with WaveSurfer.js waveform instances per sample in the queue drill-down view
- Annotation spans rendered as colored regions on the waveform — each annotator gets a distinct color (blue, red, green, orange, purple)
- Region labels show annotator name, span number, and transcript text
- Play buttons per span with auto-stop at span end
- Annotation cards have color-coded left borders matching their region color on the waveform
- Waveform instances tracked and properly cleaned up on tab switch or reload

### Unit test suite
- Added `pytest` to `[project.optional-dependencies] test` in `pyproject.toml`
- Created `tests/test_app.py` with 63 tests covering all backend functionality:
  - **Auth** (8 tests): login success/failure, empty/missing code, logout, `/me` authenticated/unauthenticated, `@login_required` decorator
  - **Task flow** (11 tests): rules stage, rules acknowledgement (+ idempotent), tutorial task/submit/advance/duplicate, auto-advance when no samples, calibration task/submit with results, no-samples-available
  - **Production submit & queue logic** (13 tests): task assignment, accepted submit, duplicate rejection (409), positive→positive queue routing, negative 90% close / 10% requeue (deterministic via monkeypatched `random`), two agreeing annotations close sample, disagreement marks conflict, three annotations always close, overdone after close, missing data / invalid `ui_choice` / sample-not-found validation
  - **Queue selection** (2 tests): conflict queue priority, stale assignment cleanup
  - **Admin** (17 tests): `@admin_required` guard, user CRUD (create with auto-code, empty name, duplicate code), user update/not-found, stage reset with annotation deletion, sample CRUD (create/invalid type/list/filter/update/not-found), tutorial delete allowed / production delete blocked, sample annotations view, queue overview with/without filter, pick-for-onboarding success/invalid type
  - **Export** (3 tests): TSV and JSON format, sample_type filter
  - **Database** (4 tests): table creation, `init_db` idempotency, WAL mode, foreign keys enabled
- Each test uses a fresh temporary SQLite database via `monkeypatch` + `tmp_path`
- `auto_export` monkeypatched in production tests to avoid file I/O and git calls

### Additional edge-case test coverage
- Expanded `tests/test_app.py` from 63 to 72 tests to cover previously missing edge cases
- Added tests for `/api/rules` content and missing-file behavior
- Added tests for `/audio/<path>` serving and path sanitization
- Added deterministic queue-selection tests for normalized weights and skipping samples already annotated by the same user
- Added export-content tests that validate actual JSON/TSV row contents, not just response status and content type
- Added a duplicate-race regression test against the database `UNIQUE(sample_id, user_id)` constraint

### Duplicate submit race handling
- Added `_insert_annotation()` helper in `webapp/app.py` to handle insert-time duplicate races cleanly
- Tutorial, calibration, and production submit paths now convert `sqlite3.IntegrityError` from duplicate annotation inserts into the expected duplicate response instead of failing with a server error

### Deployment and backup hardening
- Updated `deploy.sh` to enforce Python 3.10+ instead of only printing the interpreter version
- Changed default Gunicorn worker count from 2 to 1 to better match SQLite/WAL deployment on a small server
- Updated `backup.sh` to support `ANNOTATION_DB` and `BACKUP_DIR` environment variables
- Added explicit `sqlite3` availability check to `backup.sh`
- Updated `deployment.md` with safer WAL-mode restore instructions, including stopping the service and removing `annotations.db-wal` / `annotations.db-shm`
- Updated `deployment.md` with file ownership/write-permission requirements for the service user and more explicit systemd environment configuration
