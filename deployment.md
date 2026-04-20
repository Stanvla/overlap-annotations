# Deployment Guide — Overlap Annotation App

## Prerequisites

- **Python 3.10+**
- **git**
- **sqlite3** (for backups)
- A Linux server with shell access

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

## 3. Deploy

Run the included deployment script:

```bash
bash deploy.sh
```

This will:
1. Create a Python virtual environment in `.venv/`
2. Install all dependencies + gunicorn
3. Generate and persist a `SECRET_KEY` (saved to `.secret_key`)
4. Start the server on `http://0.0.0.0:5000`

### Configuration via environment variables

| Variable        | Default                | Description                              |
|-----------------|------------------------|------------------------------------------|
| `PORT`          | `5000`                 | Server port                              |
| `HOST`          | `0.0.0.0`              | Bind address                             |
| `WORKERS`       | `2`                    | Gunicorn worker processes                |
| `SECRET_KEY`    | Auto-generated         | Flask session signing key                |
| `ANNOTATION_DB` | `./annotations.db`     | Path to SQLite database file             |
| `EXPORT_DIR`    | Project root           | Where auto-exported TSV/JSON are written |

Example with custom settings:

```bash
PORT=8080 WORKERS=4 bash deploy.sh
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
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    --timeout 120 \
    webapp.app:app
Environment=SECRET_KEY=<your-secret-key>
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
Ensure `selected_audios/` exists and contains the `.wav` files. The app serves them from this directory.

**Users can't log in after redeployment:**
Make sure `SECRET_KEY` is the same as before. The deployment script persists it to `.secret_key` automatically. If you lost it, users will need to log in again (their data is safe in the DB).

**Restoring from backup:**
```bash
cp backups/annotations_YYYYMMDD_HHMMSS.db annotations.db
sudo systemctl restart overlap-annotations
```
