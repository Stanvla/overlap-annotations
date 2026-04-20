# Deployment Guide — Overlap Annotation App

## Prerequisites

- **Python 3.10+**
- **git**
- **git-lfs** (optional, if you keep `selected_audios.tar.gz` in Git LFS)
- **sqlite3** (for backups)
- A Linux server with shell access

If `git lfs` is not available on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git-lfs
git lfs install
```

---

## 1. Get the code onto the server

```bash
# Option A: clone from git
git clone <your-repo-url> /opt/overlap-annotations
cd /opt/overlap-annotations

# Option B: copy from local machine
scp -r /path/to/overlap-annotations user@server:/opt/overlap-annotations
ssh user@server
cd /opt/overlap-annotations
```

## 2. Copy data files (if not in git)

These files are gitignored and must be transferred manually:

```bash
# Audio files
scp -r selected_audios/ user@server:/opt/overlap-annotations/

# Database (contains all users, samples, annotations)
scp annotations.db user@server:/opt/overlap-annotations/
```

> **If starting fresh** (no existing database), the app will create a new one automatically on first run.

`annotation_pool.tsv` is tracked in normal git and now stores project-relative audio paths such as `selected_audios/000018.wav`, so it can be used directly on the server without rewriting machine-specific absolute paths.

### Optional: ship audio as one Git LFS archive

If the audio dataset is mostly fixed and you want a simpler deployment workflow, you can store one archive such as `selected_audios.tar.gz` in Git LFS instead of syncing the whole `selected_audios/` directory separately.

Recommended archive format on Linux:

```bash
tar -czf selected_audios.tar.gz selected_audios/
```

Recommended Git LFS tracking:

```bash
git lfs install
git lfs track "selected_audios.tar.gz"
git add .gitattributes selected_audios.tar.gz
git commit -m "Track audio archive with Git LFS"
```

On the server:

```bash
git lfs pull
```

The deployment script will automatically extract `selected_audios.tar.gz` into `selected_audios/` if the directory is missing.

## 3. Deploy

Run the included deployment script:

```bash
bash deploy.sh
```

This will:
1. Create a Python virtual environment in `.venv/`
2. Install all dependencies + gunicorn
3. Extract `selected_audios.tar.gz` into `selected_audios/` if the directory is missing and the archive is present
4. Generate and persist a `SECRET_KEY` (saved to `.secret_key`)
5. Start the server on `http://0.0.0.0:5000`

### Configuration via environment variables

| Variable        | Default                | Description                              |
|-----------------|------------------------|------------------------------------------|
| `PORT`          | `5000`                 | Server port                              |
| `HOST`          | `0.0.0.0`              | Bind address                             |
| `WORKERS`       | `1`                    | Gunicorn worker processes                |
| `SECRET_KEY`    | Auto-generated         | Flask session signing key                |
| `ANNOTATION_DB` | `./annotations.db`     | Path to SQLite database file             |
| `EXPORT_DIR`    | Project root           | Where auto-exported TSV/JSON are written |
| `AUDIO_ARCHIVE` | `./selected_audios.tar.gz` | Archive to extract into `selected_audios/` |
| `FORCE_AUDIO_EXTRACT` | `0`              | Re-extract archive even if `selected_audios/` exists |

Example with custom settings:

```bash
PORT=8080 WORKERS=4 bash deploy.sh
```

Example forcing archive re-extraction:

```bash
FORCE_AUDIO_EXTRACT=1 bash deploy.sh
```

## 4. Run as a systemd service (recommended)

Create `/etc/systemd/system/overlap-annotations.service`:

```ini
[Unit]
Description=Overlap Annotation App
After=network.target

[Service]
Type=exec
User=www-data
WorkingDirectory=/opt/overlap-annotations
ExecStart=/opt/overlap-annotations/.venv/bin/gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 1 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120 \
    webapp.app:app
Environment=SECRET_KEY=<your-secret-key>
Environment=ANNOTATION_DB=/opt/overlap-annotations/annotations.db
Environment=EXPORT_DIR=/opt/overlap-annotations
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable overlap-annotations
sudo systemctl start overlap-annotations
sudo systemctl status overlap-annotations
```

View logs:

```bash
journalctl -u overlap-annotations -f
```

### File ownership and write permissions

If you keep `User=www-data`, that user must be able to write:

- `annotations.db`
- `annotations.db-wal`
- `annotations.db-shm`
- `annotations_export.tsv`
- `annotations_export.json`
- `backups/`
- `.secret_key`

Example:

```bash
sudo chown -R www-data:www-data /opt/overlap-annotations
sudo chmod 600 /opt/overlap-annotations/.secret_key
```

If you use a different service user, adjust ownership accordingly.

## 5. Set up a reverse proxy (optional, for HTTPS)

Example nginx config (`/etc/nginx/sites-available/overlap-annotations`):

```nginx
server {
    listen 80;
    server_name annotations.example.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then enable and add HTTPS with certbot:

```bash
sudo ln -s /etc/nginx/sites-available/overlap-annotations /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d annotations.example.com
```

## 6. Set up automated backups

The included `backup.sh` creates safe SQLite backups (handles WAL mode correctly) and keeps the last 10.

### Manual backup

```bash
bash backup.sh
```

### Automated backup via cron (every 6 hours)

```bash
crontab -e
```

Add:

```
0 */6 * * * /opt/overlap-annotations/backup.sh >> /opt/overlap-annotations/backups/backup.log 2>&1
```

If you changed the database location, pass it explicitly in cron:

```
0 */6 * * * ANNOTATION_DB=/opt/overlap-annotations/annotations.db BACKUP_DIR=/opt/overlap-annotations/backups /opt/overlap-annotations/backup.sh >> /opt/overlap-annotations/backups/backup.log 2>&1
```

Backups are stored in `backups/` as `annotations_YYYYMMDD_HHMMSS.db`.

## 7. Auto-exported annotation files

After every production annotation, the app automatically writes:

- `annotations_export.tsv` — tab-separated, all production annotations
- `annotations_export.json` — structured JSON with full span data

These are also auto-committed to git (if a git repo is present). You can additionally download them anytime from the admin panel using the **⇓ Export TSV** / **⇓ Export JSON** buttons.

---

## Important files

| File / Directory       | Tracked in git | Description                            |
|------------------------|:--------------:|----------------------------------------|
| `webapp/`              | ✓              | Flask application code                 |
| `static/index.html`    | ✓              | Frontend (single-page app)             |
| `deploy.sh`            | ✓              | Deployment script                      |
| `backup.sh`            | ✓              | Backup script                          |
| `pyproject.toml`       | ✓              | Python package config                  |
| `annotatori_pravidla_overlap.md` | ✓    | Annotation rules (served to users)     |
| `annotation_pool.tsv`   | ✓              | Import pool with relative `selected_audios/...` paths |
| `annotations_export.*` | ✓              | Auto-exported annotations              |
| `annotations.db`       | ✗              | SQLite database (all app data)         |
| `selected_audios/`     | ✗              | Audio files (~1500 .wav)               |
| `.secret_key`          | ✗              | Flask session secret                   |
| `backups/`             | ✗              | Database backup snapshots              |

---

## Troubleshooting

**App won't start — port in use:**
```bash
PORT=8080 bash deploy.sh
```

**Database locked errors:**
SQLite WAL mode handles concurrent reads well. For a small team (< 10 users) this is fine. If you see locking issues, reduce gunicorn workers to 1.

**Audio files not playing:**
Ensure `selected_audios/` exists and contains the `.wav` files. If you use the archive workflow, confirm that `selected_audios.tar.gz` was fully downloaded via Git LFS and extracted successfully.

**Importing from annotation_pool.tsv on the server:**
The TSV now uses relative paths like `selected_audios/000018.wav`. Keep the extracted audio files under `selected_audios/` in the project root so imported samples resolve correctly.

**Users can't log in after redeployment:**
Make sure `SECRET_KEY` is the same as before. The deployment script persists it to `.secret_key` automatically. If you lost it, users will need to log in again (their data is safe in the DB).

**Restoring from backup:**
```bash
sudo systemctl stop overlap-annotations
cp backups/annotations_YYYYMMDD_HHMMSS.db annotations.db
rm -f annotations.db-wal annotations.db-shm
sudo chown www-data:www-data annotations.db
sudo systemctl restart overlap-annotations
```

If your service runs as a user other than `www-data`, replace the `chown` target accordingly.
