"""Import samples from annotation_pool.tsv into the database."""
import csv
import json
import os
import sys
import secrets

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from webapp.db import init_db, get_db


def normalize_audio_path(audio_path):
    normalized = str(audio_path).replace("\\", "/").strip()
    normalized = normalized.removeprefix("./")

    marker = "/selected_audios/"
    if marker in normalized:
        return f"selected_audios/{normalized.split(marker, 1)[1]}"
    if normalized.startswith("selected_audios/"):
        return normalized
    return f"selected_audios/{normalized.lstrip('/')}"


def import_production_samples(tsv_path):
    """Import production samples from the TSV pool."""
    db = get_db()

    existing = db.execute("SELECT COUNT(*) as c FROM samples WHERE sample_type = 'production'").fetchone()["c"]
    if existing > 0:
        print(f"Already have {existing} production samples. Skipping import.")
        db.close()
        return

    count = 0
    with open(tsv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            audio_path = normalize_audio_path(row["audio_path"])
            recognized_text = row.get("prediction", "")
            metadata = {k: row[k] for k in row if k not in ("audio_path", "prediction")}

            db.execute(
                """INSERT INTO samples (sample_type, audio_path, recognized_text, queue_type, metadata_json)
                   VALUES ('production', ?, ?, 'unseen', ?)""",
                (audio_path, recognized_text, json.dumps(metadata))
            )
            count += 1

    db.commit()
    db.close()
    print(f"Imported {count} production samples.")


def create_admin_user():
    """Create a default admin user if none exists."""
    db = get_db()
    admin = db.execute("SELECT id FROM users WHERE is_admin = 1").fetchone()
    if admin:
        print("Admin user already exists.")
        db.close()
        return

    code = secrets.token_hex(4)
    db.execute(
        "INSERT INTO users (login_code, display_name, is_admin, stage) VALUES (?, ?, 1, 'production')",
        (code, "Admin")
    )
    db.commit()
    db.close()
    print(f"Created admin user with login code: {code}")


if __name__ == "__main__":
    init_db()

    tsv_path = os.path.join(os.path.dirname(__file__), "..", "annotation_pool.tsv")
    if os.path.exists(tsv_path):
        import_production_samples(tsv_path)
    else:
        print(f"No TSV file found at {tsv_path}")

    create_admin_user()
    print("Done. You can now run the app with: python -m webapp.run")
