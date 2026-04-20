# Database Transfer Guide

This guide explains how to safely transfer the SQLite database for the overlap annotation app to a server.

The application uses SQLite in WAL mode, so the safest method is:

1. create a proper backup snapshot with `backup.sh`
2. copy that snapshot to the server
3. restore it as `annotations.db`
4. remove any stale `annotations.db-wal` and `annotations.db-shm` files on the server

Do **not** copy the live `annotations.db` file directly while the app is running. In WAL mode, the newest writes may still be in the WAL file.

## Files involved

- `annotations.db`: main SQLite database file
- `annotations.db-wal`: write-ahead log file
- `annotations.db-shm`: shared-memory sidecar file
- `backups/annotations_YYYYMMDD_HHMMSS.db`: safe backup snapshot created by `backup.sh`

## Safest workflow

### On the source machine

Create a fresh snapshot:

```bash
bash backup.sh
```

Find the newest backup:

```bash
ls -1t backups/annotations_*.db | head -n 1
```

Example result:

```bash
backups/annotations_20260420_221500.db
```

Copy it to the server, but rename it to `annotations.db` during transfer if you want a simpler restore:

```bash
scp backups/annotations_20260420_221500.db user@server:/opt/overlap-annotations/annotations.db
```

If you prefer to copy it without renaming first:

```bash
scp backups/annotations_20260420_221500.db user@server:/opt/overlap-annotations/
```

## Case 1: Server app is not running yet

If the server has not started the app yet, the process is simple.

On the server:

```bash
cd /opt/overlap-annotations
ls -lh annotations.db
```

If you copied the backup under its timestamped name, rename it:

```bash
mv backups/annotations_20260420_221500.db annotations.db
```

Remove stale sidecar files if they exist:

```bash
rm -f annotations.db-wal annotations.db-shm
```

Set ownership for the service user if needed:

```bash
sudo chown www-data:www-data annotations.db
```

Then start the app normally.

## Case 2: Server app is already running

If the server app is already running, stop it before replacing the database.

On the server:

```bash
sudo systemctl stop overlap-annotations
cd /opt/overlap-annotations
```

Optional: keep a server-side safety copy before replacing the DB:

```bash
cp annotations.db annotations.db.before-transfer
```

If you copied the backup directly as `annotations.db`, keep it as-is.

If you copied the backup under a timestamped filename, move it into place:

```bash
mv annotations_20260420_221500.db annotations.db
```

Or if it is inside `backups/`:

```bash
cp backups/annotations_20260420_221500.db annotations.db
```

Now remove any stale WAL/SHM files:

```bash
rm -f annotations.db-wal annotations.db-shm
```

Fix ownership for the service user:

```bash
sudo chown www-data:www-data annotations.db
```

Start the service again:

```bash
sudo systemctl start overlap-annotations
sudo systemctl status overlap-annotations
```

## If your service user is not `www-data`

Replace `www-data:www-data` with the actual service user and group.

Example:

```bash
sudo chown myappuser:myappuser annotations.db
```

## Quick verification after transfer

Check the file exists and has a reasonable size:

```bash
ls -lh /opt/overlap-annotations/annotations.db
```

Check the database opens:

```bash
sqlite3 /opt/overlap-annotations/annotations.db ".tables"
```

Optionally inspect row counts:

```bash
sqlite3 /opt/overlap-annotations/annotations.db "SELECT COUNT(*) FROM users;"
sqlite3 /opt/overlap-annotations/annotations.db "SELECT COUNT(*) FROM samples;"
sqlite3 /opt/overlap-annotations/annotations.db "SELECT COUNT(*) FROM annotations;"
```

If the app is running, test it by:

1. opening the login page
2. confirming users can log in
3. loading one task
4. checking the admin panel still opens for the admin account

## Recommended transfer commands

### Minimal safe source command

```bash
bash backup.sh
scp "$(ls -1t backups/annotations_*.db | head -n 1)" user@server:/opt/overlap-annotations/annotations.db
```

### Minimal safe server command when service already exists

```bash
sudo systemctl stop overlap-annotations
cd /opt/overlap-annotations
rm -f annotations.db-wal annotations.db-shm
sudo chown www-data:www-data annotations.db
sudo systemctl start overlap-annotations
```

## Common mistakes to avoid

- Do not copy only `annotations.db` from a live running app and assume it contains the latest writes.
- Do not commit the live database to git or Git LFS as your main transfer mechanism.
- Do not leave stale `annotations.db-wal` or `annotations.db-shm` files in place after restoring an older snapshot.
- Do not forget file ownership if the service runs as `www-data` or another non-login user.

## If you want a rollback plan

Before replacing the DB on the server, save a quick local copy:

```bash
cp annotations.db annotations.db.before-transfer
```

If something goes wrong, stop the service and restore it:

```bash
sudo systemctl stop overlap-annotations
mv annotations.db.before-transfer annotations.db
rm -f annotations.db-wal annotations.db-shm
sudo chown www-data:www-data annotations.db
sudo systemctl start overlap-annotations
```

## Summary

Best practice for this project:

- create a snapshot with `backup.sh`
- transfer the snapshot to the server
- restore it as `annotations.db`
- remove stale WAL/SHM files
- fix ownership
- start or restart the app

That is the safest and simplest database transfer flow for the current SQLite/WAL setup.