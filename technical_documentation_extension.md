# Technical Documentation Extension

Additional functionality implemented beyond the original [technical_documentation.md](technical_documentation.md) specification.

---

## 1. Waveform Visualization & Audio Controls

### Interactive Waveform (WaveSurfer.js v7)

The annotation interface uses an interactive waveform instead of a plain `<audio>` element. Annotators can:

- See the full audio waveform rendered as a bar chart
- Click anywhere on the waveform to seek
- Drag on the waveform to create overlap span regions (for "positive, localizable" annotations)
- Each span region is color-coded (cycling through blue, red, green, orange, purple at 20–25% opacity)

### Playback Speed Control

A speed selector (`0.5×`, `0.75×`, `1×`, `1.25×`, `1.5×`, `2×`) is available next to the waveform. The selected speed:

- Applies to all playback (full audio, individual spans, loop mode)
- Persists across samples within the same session

### Span Playback & Loop

Each created span has two buttons:

- **▶ Play** — plays the span once and auto-stops at the span's end time
- **🔁 Loop** — toggles loop mode; when active, playback automatically restarts at the span's start when reaching its end

### Time Display

A real-time display shows `current / total` duration in `M:SS.mm` format, updated continuously during playback.

---

## 2. Tutorial & Calibration Feedback Visualization

### Tutorial Feedback with Waveform Regions

After submitting a tutorial annotation, the correct answer is shown with:

- Golden spans rendered as **green regions** (`rgba(34, 197, 94, 0.25)`) on the existing waveform
- **Play buttons** for each golden span: `▶ Span 1 (1.42s–2.87s)` — clicking plays that exact region and auto-stops
- Text details: span times, intelligibility level, and transcribed text (if any)

This allows the annotator to listen to the correct spans and understand the expected annotation.

### Calibration Results with Individual Waveforms

When calibration is complete, each sample in the results summary has:

- Its own waveform instance (not just an `<audio>` tag)
- Golden span regions shown as green highlights
- Play buttons per golden span with auto-stop
- Match/mismatch indicator with color-coded borders (green for match, red for mismatch)
- Full span detail text (times, intelligibility, transcript)

Waveform instances are cleaned up when navigating away.

---

## 3. Annotation Rules Display

### Rules Endpoint

The annotation rules document (`annotatori_pravidla_overlap.md`) is served via `GET /api/rules` and rendered client-side with a lightweight Markdown-to-HTML converter (supports headers, bold, code, lists).

### Rules Workflow

- Users see the rules on their first login (must acknowledge before starting tutorial)
- Rules are accessible anytime via the **ℹ️ Pravidla** button in the header, which opens a scrollable modal
- Rules content is cached after the first fetch

---

## 4. Admin Panel Extensions

### User Management

| Feature | Description |
|---------|-------------|
| Create user | Form with display name, optional login code (auto-generated via `secrets.token_hex(4)`), admin checkbox |
| Reset user | Sends user back to rules/tutorial/calibration stage. **Automatically deletes** their tutorial and calibration annotations so they can redo onboarding without "already submitted" errors |
| View all users | Table showing ID, name, login code, current stage, production annotation count, admin flag |

### Tutorial/Calibration Sample Management

| Feature | Endpoint | Description |
|---------|----------|-------------|
| Pick from annotated samples | `POST /api/admin/samples/pick-for-onboarding` | Selects production samples that have accepted annotations, creates tutorial/calibration copies with golden annotations auto-derived from the first accepted annotation |
| Delete sample | `DELETE /api/admin/samples/{id}` | Removes a tutorial/calibration sample and its annotations (production samples cannot be deleted) |
| Set golden: Negative | `PUT /api/admin/samples/{id}` | Quick-set button, no modal needed |
| Set golden: Positive (not localizable) | `PUT /api/admin/samples/{id}` | Quick-set button, no modal needed |
| Set golden: Positive (localizable) | `PUT /api/admin/samples/{id}` | Opens a full modal with waveform, drag-to-create spans, intelligibility selector, transcript textarea |

### Golden Annotation Modal

For "positive, localizable" golden annotations, admins get a dedicated modal with:

- Full waveform with drag-to-create span regions
- Per-span controls: intelligibility dropdown, transcript text area, delete button
- Play buttons per span
- Save/Cancel actions

### Golden Annotation Display in Sample Cards

Admin sample cards show full golden annotation details:

- Choice label (e.g., "Overlap, localizable")
- Span count
- Per-span details: start/end times, intelligibility level, transcribed text

### Production Samples Tab

- Read-only list of production samples with queue type, closed status, accepted annotation count
- "View" button per sample opens all annotations with user name, label, status, timestamp, and full `annotation_data` JSON

---

## 5. Annotation Export

### Auto-Export After Each Production Submission

After every accepted production annotation, the app automatically writes:

- **`annotations_export.tsv`** — tab-separated file with columns: `annotation_id`, `sample_id`, `sample_type`, `audio_path`, `recognized_text`, `user_id`, `display_name`, `label`, `ui_choice`, `span_count`, `spans_json`, `status`, `is_closed`, `accepted_annotation_count`, `queue_type`, `created_at`
- **`annotations_export.json`** — structured JSON array with spans fully expanded

Export is best-effort and will not break the annotation flow if it fails.

### Git Auto-Commit

After writing export files, the app runs:

```
git add annotations_export.tsv annotations_export.json
git commit -m "auto: update annotation exports" --no-verify
```

This creates a version history of annotation progress. Silently skipped if git is not available.

### Admin Manual Export

Two buttons in the admin panel header:

- **⇓ Export TSV** — downloads all annotations (all sample types) as a TSV file
- **⇓ Export JSON** — downloads all annotations as a JSON file

Endpoint: `GET /api/admin/export?format={tsv|json}&sample_type={optional filter}`

---

## 6. Database Backup

### backup.sh

A shell script that creates safe SQLite backups:

- Uses SQLite's `.backup` command (correctly handles WAL journal mode)
- Saves to `backups/annotations_YYYYMMDD_HHMMSS.db`
- Keeps the last 10 backups, automatically removes older ones
- Can be run via cron for automated backups (e.g., every 6 hours)

---

## 7. Deployment

### deploy.sh

A deployment script that:

1. Checks for Python 3.10+
2. Creates a virtual environment in `.venv/`
3. Installs all dependencies + gunicorn
4. Generates a stable `SECRET_KEY` (persisted to `.secret_key` with `chmod 600`)
5. Starts gunicorn with configurable workers, port, and host

Configurable via environment variables: `PORT`, `HOST`, `WORKERS`, `SECRET_KEY`, `EXPORT_DIR`.

See [deployment.md](deployment.md) for full deployment instructions.

---

## 8. UI/UX Enhancements

| Feature | Description |
|---------|-------------|
| Stage badge | Color-coded badge in the header: yellow (tutorial), indigo (calibration), green (production) |
| Progress bar | Visual progress indicator for tutorial/calibration: "Tutorial 2 / 5" with fill bar |
| Recognized text | Transcript shown above the waveform during annotation for context |
| Submit button state | Disabled until a choice is selected; disabled during submission to prevent double-submit |
| Session persistence | Page load checks for existing session and auto-restores the user's state |
| Admin visibility | Admin button shown only for admin users |
| Production annotation counter | Displayed next to the user's name as "(X annotated)". Counts only accepted production annotations (excludes tutorial/calibration). Updates live after each submission. Also shown in the admin user table as an "Annotated" column |

---

## 9. Security Measures

| Measure | Description |
|---------|-------------|
| Audio path sanitization | `os.path.basename()` strips directory traversal attempts; only serves files from `selected_audios/` |
| Session-based auth | Cookie-signed sessions via Flask's `SECRET_KEY` |
| Admin-only endpoints | `@admin_required` decorator checks `is_admin` flag before allowing access |
| UNIQUE constraint | `UNIQUE(sample_id, user_id)` on annotations prevents duplicate submissions at the database level |
| WAL journal mode | SQLite WAL mode for safe concurrent reads during annotation |
