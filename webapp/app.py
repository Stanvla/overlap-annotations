import json
import random
import secrets
import csv
import io
import sqlite3
import mimetypes
import posixpath

from flask import Flask, request, jsonify, session, send_from_directory, send_file, Response
from functools import wraps
import os
from urllib.parse import quote

from .db import get_db, init_db

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "..", "static"))
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AUDIO_DIR = os.environ.get("AUDIO_DIR", os.path.join(PROJECT_ROOT, "selected_audios"))
EXPORT_DIR = os.environ.get("EXPORT_DIR", PROJECT_ROOT)

NEGATIVE_REQUEUE_PROB = 0.1

QUEUE_WEIGHTS = {
    "positive": 0.45,
    "unseen": 0.45,
    "negative": 0.10,
}


def _normalize_audio_path(audio_path):
    if not audio_path:
        return ""

    normalized = str(audio_path).replace("\\", "/").strip()
    normalized = normalized.removeprefix("./")

    marker = "/selected_audios/"
    if marker in normalized:
        return f"selected_audios/{normalized.split(marker, 1)[1]}"
    if normalized.startswith("selected_audios/"):
        return normalized
    return normalized


def _audio_request_path(audio_path):
    normalized = _normalize_audio_path(audio_path)
    if normalized.startswith("selected_audios/"):
        normalized = normalized[len("selected_audios/"):]
    return normalized.lstrip("/")


def _audio_url(audio_path):
    return f"/audio/{quote(_audio_request_path(audio_path), safe='/')}"


def _requested_audio_fs_path(filename):
    requested = filename.replace("\\", "/")
    if requested.startswith("selected_audios/"):
        requested = requested[len("selected_audios/"):]

    normalized = posixpath.normpath(requested).lstrip("/")
    if normalized in ("", ".", "..") or normalized.startswith("../"):
        return None
    return os.path.join(AUDIO_DIR, normalized)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        db = get_db()
        user = db.execute("SELECT is_admin FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        db.close()
        if not user or not user["is_admin"]:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


def _user_dict(row, db=None):
    d = {
        "id": row["id"],
        "display_name": row["display_name"],
        "stage": row["stage"],
        "tutorial_index": row["tutorial_index"],
        "calibration_index": row["calibration_index"],
        "current_sample_id": row["current_sample_id"],
        "is_admin": bool(row["is_admin"]),
        "onboarding_completed_at": row["onboarding_completed_at"],
    }
    if db:
        count = db.execute(
            """SELECT COUNT(*) as c FROM annotations a
               JOIN samples s ON a.sample_id = s.id
               WHERE a.user_id = ? AND s.sample_type = 'production' AND a.status = 'accepted'""",
            (row["id"],)
        ).fetchone()["c"]
        d["production_annotation_count"] = count
    return d


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    code = data.get("login_code", "").strip()
    if not code:
        return jsonify({"error": "Login code required"}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE login_code = ?", (code,)).fetchone()

    if not user:
        db.close()
        return jsonify({"error": "Invalid login code"}), 401

    session["user_id"] = user["id"]
    result = _user_dict(user, db)
    db.close()
    return jsonify({"user": result})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
@login_required
def me():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        db.close()
        session.clear()
        return jsonify({"error": "User not found"}), 401
    result = _user_dict(user, db)
    db.close()
    return jsonify({"user": result})


# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------

def _sample_dict(row, include_golden=False):
    d = {
        "id": row["id"],
        "sample_type": row["sample_type"],
        "audio_url": _audio_url(row["audio_path"]),
        "recognized_text": row["recognized_text"],
    }
    if include_golden and row["golden_annotation"]:
        d["golden_annotation"] = json.loads(row["golden_annotation"])
    return d


def _get_tutorial_sample(db, user):
    idx = user["tutorial_index"]
    sample = db.execute(
        "SELECT * FROM samples WHERE sample_type = 'tutorial' ORDER BY sort_order, id LIMIT 1 OFFSET ?",
        (idx,)
    ).fetchone()
    return sample


def _get_calibration_sample(db, user):
    idx = user["calibration_index"]
    sample = db.execute(
        "SELECT * FROM samples WHERE sample_type = 'calibration' ORDER BY sort_order, id LIMIT 1 OFFSET ?",
        (idx,)
    ).fetchone()
    return sample


def _insert_annotation(db, sample_id, user_id, label, annotation_data, status):
    try:
        db.execute(
            "INSERT INTO annotations (sample_id, user_id, label, annotation_data, status) VALUES (?, ?, ?, ?, ?)",
            (sample_id, user_id, label, json.dumps(annotation_data), status)
        )
        return True
    except sqlite3.IntegrityError as exc:
        try:
            db.rollback()
        except Exception:
            pass
        if "UNIQUE constraint failed" in str(exc) and "annotations.sample_id, annotations.user_id" in str(exc):
            return False
        raise


def _pick_production_sample(db, user_id):
    # Try conflict queue first
    sample = db.execute("""
        SELECT s.* FROM samples s
        WHERE s.sample_type = 'production' AND s.is_closed = 0 AND s.queue_type = 'conflict'
        AND s.id NOT IN (SELECT sample_id FROM annotations WHERE user_id = ?)
        ORDER BY RANDOM() LIMIT 1
    """, (user_id,)).fetchone()
    if sample:
        return sample

    # Check which queues are non-empty (excluding already-annotated by user)
    available = {}
    for qt in ("positive", "unseen", "negative"):
        count = db.execute("""
            SELECT COUNT(*) as c FROM samples s
            WHERE s.sample_type = 'production' AND s.is_closed = 0 AND s.queue_type = ?
            AND s.id NOT IN (SELECT sample_id FROM annotations WHERE user_id = ?)
        """, (qt, user_id)).fetchone()["c"]
        if count > 0:
            available[qt] = count

    if not available:
        return None

    # Normalize weights over non-empty queues
    total_weight = sum(QUEUE_WEIGHTS[q] for q in available)
    normalized = {q: QUEUE_WEIGHTS[q] / total_weight for q in available}

    # Weighted random choice
    r = random.random()
    cumulative = 0.0
    chosen_queue = list(available.keys())[0]
    for q, w in normalized.items():
        cumulative += w
        if r <= cumulative:
            chosen_queue = q
            break

    sample = db.execute("""
        SELECT s.* FROM samples s
        WHERE s.sample_type = 'production' AND s.is_closed = 0 AND s.queue_type = ?
        AND s.id NOT IN (SELECT sample_id FROM annotations WHERE user_id = ?)
        ORDER BY RANDOM() LIMIT 1
    """, (chosen_queue, user_id)).fetchone()

    return sample


@app.route("/api/task/current")
@login_required
def get_current_task():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if user["stage"] == "rules":
        db.close()
        return jsonify({"mode": "rules"})

    if user["stage"] == "tutorial":
        sample = _get_tutorial_sample(db, user)
        if not sample:
            # No more tutorial samples — advance to calibration
            db.execute("UPDATE users SET stage = 'calibration', tutorial_index = 0 WHERE id = ?", (user["id"],))
            db.commit()
            user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
            # Fall through to calibration
        else:
            total = db.execute("SELECT COUNT(*) as c FROM samples WHERE sample_type = 'tutorial'").fetchone()["c"]
            db.close()
            return jsonify({
                "mode": "tutorial",
                "index": user["tutorial_index"],
                "total": total,
                "sample": _sample_dict(sample),
            })

    if user["stage"] == "calibration":
        sample = _get_calibration_sample(db, user)
        if not sample:
            # No more calibration — advance to production
            db.execute("""
                UPDATE users
                SET stage = 'production', calibration_index = 0, onboarding_completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (user["id"],))
            db.commit()
            user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        else:
            total = db.execute("SELECT COUNT(*) as c FROM samples WHERE sample_type = 'calibration'").fetchone()["c"]
            db.close()
            return jsonify({
                "mode": "calibration",
                "index": user["calibration_index"],
                "total": total,
                "sample": _sample_dict(sample),
            })

    # Production
    if user["current_sample_id"]:
        sample = db.execute("SELECT * FROM samples WHERE id = ?", (user["current_sample_id"],)).fetchone()
        if sample and not sample["is_closed"]:
            # Check user hasn't already annotated it
            existing = db.execute(
                "SELECT id FROM annotations WHERE sample_id = ? AND user_id = ?",
                (sample["id"], user["id"])
            ).fetchone()
            if not existing:
                db.close()
                return jsonify({
                    "mode": "production",
                    "sample": _sample_dict(sample),
                })
        # Clear stale assignment
        db.execute("UPDATE users SET current_sample_id = NULL WHERE id = ?", (user["id"],))
        db.commit()

    # Assign a new production sample
    sample = _pick_production_sample(db, user["id"])
    if not sample:
        db.close()
        return jsonify({"mode": "production", "sample": None, "message": "No samples available"})

    db.execute("UPDATE users SET current_sample_id = ? WHERE id = ?", (sample["id"], user["id"]))
    db.commit()
    db.close()
    return jsonify({
        "mode": "production",
        "sample": _sample_dict(sample),
    })


@app.route("/api/task/submit", methods=["POST"])
@login_required
def submit_task():
    data = request.get_json(force=True)
    sample_id = data.get("sample_id")
    annotation_data = data.get("annotation_data")

    if not sample_id or not annotation_data:
        return jsonify({"error": "sample_id and annotation_data required"}), 400

    ui_choice = annotation_data.get("ui_choice")
    if ui_choice == "negative":
        label = "negative"
    elif ui_choice in ("positive_not_localizable", "positive_localizable"):
        label = "positive"
    else:
        return jsonify({"error": "Invalid ui_choice"}), 400

    user_id = session["user_id"]
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    sample = db.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()

    if not sample:
        db.close()
        return jsonify({"error": "Sample not found"}), 404

    # ---- Tutorial submit ----
    if user["stage"] == "tutorial":
        # Check duplicate
        existing = db.execute(
            "SELECT id FROM annotations WHERE sample_id = ? AND user_id = ?",
            (sample_id, user_id)
        ).fetchone()
        if existing:
            db.close()
            return jsonify({"error": "Already submitted"}), 409

        if not _insert_annotation(db, sample_id, user_id, label, annotation_data, "accepted"):
            db.close()
            return jsonify({"error": "Already submitted"}), 409

        new_idx = user["tutorial_index"] + 1
        total_tutorials = db.execute("SELECT COUNT(*) as c FROM samples WHERE sample_type = 'tutorial'").fetchone()["c"]

        if new_idx >= total_tutorials:
            db.execute("UPDATE users SET stage = 'calibration', tutorial_index = ? WHERE id = ?", (new_idx, user_id))
        else:
            db.execute("UPDATE users SET tutorial_index = ? WHERE id = ?", (new_idx, user_id))

        db.commit()

        # Return feedback
        golden = json.loads(sample["golden_annotation"]) if sample["golden_annotation"] else None
        db.close()
        return jsonify({
            "result": "accepted",
            "feedback": golden,
            "stage": "calibration" if new_idx >= total_tutorials else "tutorial",
        })

    # ---- Calibration submit ----
    if user["stage"] == "calibration":
        existing = db.execute(
            "SELECT id FROM annotations WHERE sample_id = ? AND user_id = ?",
            (sample_id, user_id)
        ).fetchone()
        if existing:
            db.close()
            return jsonify({"error": "Already submitted"}), 409

        if not _insert_annotation(db, sample_id, user_id, label, annotation_data, "accepted"):
            db.close()
            return jsonify({"error": "Already submitted"}), 409

        new_idx = user["calibration_index"] + 1
        total_calib = db.execute("SELECT COUNT(*) as c FROM samples WHERE sample_type = 'calibration'").fetchone()["c"]

        if new_idx >= total_calib:
            db.execute("""
                UPDATE users
                SET stage = 'production', calibration_index = ?, onboarding_completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_idx, user_id))
            db.commit()

            # Return all calibration results
            results = []
            cal_samples = db.execute(
                "SELECT * FROM samples WHERE sample_type = 'calibration' ORDER BY sort_order, id"
            ).fetchall()
            for cs in cal_samples:
                ann = db.execute(
                    "SELECT * FROM annotations WHERE sample_id = ? AND user_id = ?",
                    (cs["id"], user_id)
                ).fetchone()
                results.append({
                    "sample": _sample_dict(cs),
                    "golden": json.loads(cs["golden_annotation"]) if cs["golden_annotation"] else None,
                    "your_answer": json.loads(ann["annotation_data"]) if ann else None,
                })

            db.close()
            return jsonify({
                "result": "accepted",
                "stage": "production",
                "calibration_results": results,
            })
        else:
            db.execute("UPDATE users SET calibration_index = ? WHERE id = ?", (new_idx, user_id))
            db.commit()
            db.close()
            return jsonify({
                "result": "accepted",
                "stage": "calibration",
            })

    # ---- Production submit ----
    # Step 1: check duplicate
    existing = db.execute(
        "SELECT id FROM annotations WHERE sample_id = ? AND user_id = ?",
        (sample_id, user_id)
    ).fetchone()
    if existing:
        db.execute("UPDATE users SET current_sample_id = NULL WHERE id = ?", (user_id,))
        db.commit()
        db.close()
        return jsonify({"result": "duplicate", "message": "Already submitted for this sample"}), 409

    # Step 2: check if already closed / at limit
    if sample["is_closed"] or sample["accepted_annotation_count"] >= 3:
        if not _insert_annotation(db, sample_id, user_id, label, annotation_data, "overdone"):
            db.execute("UPDATE users SET current_sample_id = NULL WHERE id = ?", (user_id,))
            db.commit()
            db.close()
            return jsonify({"result": "duplicate", "message": "Already submitted for this sample"}), 409
        db.execute("UPDATE users SET current_sample_id = NULL WHERE id = ?", (user_id,))
        db.commit()
        db.close()
        return jsonify({"result": "overdone"})

    # Step 3: store as accepted
    if not _insert_annotation(db, sample_id, user_id, label, annotation_data, "accepted"):
        db.execute("UPDATE users SET current_sample_id = NULL WHERE id = ?", (user_id,))
        db.commit()
        db.close()
        return jsonify({"result": "duplicate", "message": "Already submitted for this sample"}), 409
    new_accepted = sample["accepted_annotation_count"] + 1
    db.execute(
        "UPDATE samples SET accepted_annotation_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_accepted, sample_id)
    )

    # Recompute sample state
    accepted_labels = [r["label"] for r in db.execute(
        "SELECT label FROM annotations WHERE sample_id = ? AND status = 'accepted'",
        (sample_id,)
    ).fetchall()]

    should_close = False
    new_queue = sample["queue_type"]

    if len(accepted_labels) >= 2:
        label_set = set(accepted_labels)
        if len(label_set) == 1 and len(accepted_labels) >= 2:
            should_close = True
        elif len(accepted_labels) >= 3:
            should_close = True
        elif len(label_set) > 1:
            new_queue = "conflict"

    if not should_close and len(accepted_labels) == 1:
        # First annotation — route to queue
        if label == "negative":
            if random.random() < NEGATIVE_REQUEUE_PROB:
                new_queue = "negative"
            else:
                # stays unseen? No — once annotated it should not be unseen.
                # Per spec: negative goes to negative queue with prob 0.1
                # If not re-queued, the sample just stays where it is but
                # the spec says closed when 2 agree or 3 total, so we need to
                # leave the sample available. Let's set it to negative queue anyway
                # but let it only be picked with prob 0.1 via queue selection.
                # Re-reading spec: "added to the negative queue with probability 0.1"
                # means with 90% chance it doesn't get re-queued at all.
                # A sample that isn't re-queued and isn't closed just... won't be picked again.
                # That effectively closes it after one negative annotation (90% of the time).
                should_close = True
        else:
            new_queue = "positive"

    if should_close:
        db.execute(
            "UPDATE samples SET is_closed = 1, queue_type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_queue, sample_id)
        )
    else:
        db.execute(
            "UPDATE samples SET queue_type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_queue, sample_id)
        )

    db.execute("UPDATE users SET current_sample_id = NULL WHERE id = ?", (user_id,))
    db.commit()
    db.close()
    auto_export()
    return jsonify({"result": "accepted"})


@app.route("/api/calibration/results")
@login_required
def calibration_results():
    db = get_db()
    user_id = session["user_id"]
    cal_samples = db.execute(
        "SELECT * FROM samples WHERE sample_type = 'calibration' ORDER BY sort_order, id"
    ).fetchall()
    results = []
    for cs in cal_samples:
        ann = db.execute(
            "SELECT * FROM annotations WHERE sample_id = ? AND user_id = ?",
            (cs["id"], user_id)
        ).fetchone()
        results.append({
            "sample": _sample_dict(cs),
            "golden": json.loads(cs["golden_annotation"]) if cs["golden_annotation"] else None,
            "your_answer": json.loads(ann["annotation_data"]) if ann else None,
        })
    db.close()
    return jsonify({"results": results})


@app.route("/api/rules/acknowledge", methods=["POST"])
@login_required
def acknowledge_rules():
    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user["stage"] == "rules":
        db.execute("UPDATE users SET stage = 'tutorial' WHERE id = ?", (user_id,))
        db.commit()
    db.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "annotatori_pravidla_overlap.md")

AUDIO_MIME_TYPES = {
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}

@app.route("/api/rules")
def get_rules():
    if not os.path.isfile(RULES_PATH):
        return jsonify({"content": ""}), 404
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return jsonify({"content": f.read()})


# ---------------------------------------------------------------------------
# Audio serving
# ---------------------------------------------------------------------------

@app.route("/audio/<path:filename>")
def serve_audio(filename):
    # Sanitize — only serve files from the audio directory.
    requested_path = _requested_audio_fs_path(filename)
    if not requested_path:
        return jsonify({"error": "Not found"}), 404

    candidates = [requested_path]
    requested_root, _requested_ext = os.path.splitext(requested_path)
    flac_fallback = requested_root + ".flac"
    if flac_fallback not in candidates:
        candidates.append(flac_fallback)

    audio_path = next((path for path in candidates if os.path.isfile(path)), None)
    if not audio_path:
        return jsonify({"error": "Not found"}), 404

    extension = os.path.splitext(audio_path)[1].lower()
    mimetype = AUDIO_MIME_TYPES.get(extension) or mimetypes.guess_type(audio_path)[0] or "application/octet-stream"
    return send_file(audio_path, mimetype=mimetype)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_list_users():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    result = [
        {**_user_dict(u, db), "login_code": u["login_code"], "created_at": u["created_at"]}
        for u in users
    ]
    db.close()
    return jsonify({"users": result})


@app.route("/api/admin/users", methods=["POST"])
@admin_required
def admin_create_user():
    data = request.get_json(force=True)
    display_name = data.get("display_name", "").strip()
    if not display_name:
        return jsonify({"error": "display_name required"}), 400

    login_code = data.get("login_code") or secrets.token_hex(4)
    is_admin = 1 if data.get("is_admin") else 0

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (login_code, display_name, is_admin) VALUES (?, ?, ?)",
            (login_code, display_name, is_admin)
        )
        db.commit()
    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 400
    user = db.execute("SELECT * FROM users WHERE login_code = ?", (login_code,)).fetchone()
    db.close()
    return jsonify({"user": {**_user_dict(user), "login_code": user["login_code"]}})


@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@admin_required
def admin_update_user(user_id):
    data = request.get_json(force=True)
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    display_name = data.get("display_name", user["display_name"])
    login_code = data.get("login_code", user["login_code"])
    is_admin = int(data.get("is_admin", user["is_admin"]))
    stage = data.get("stage", user["stage"])

    # When resetting to an onboarding stage, also reset indexes
    if stage != user["stage"] and stage in ("rules", "tutorial", "calibration"):
        # Delete old tutorial/calibration annotations so user can redo them
        tut_cal_sample_ids = db.execute(
            "SELECT id FROM samples WHERE sample_type IN ('tutorial', 'calibration')"
        ).fetchall()
        if tut_cal_sample_ids:
            id_list = [r["id"] for r in tut_cal_sample_ids]
            placeholders = ",".join("?" * len(id_list))
            db.execute(
                f"DELETE FROM annotations WHERE user_id = ? AND sample_id IN ({placeholders})",
                [user_id] + id_list
            )
        db.execute(
            """UPDATE users SET display_name = ?, login_code = ?, is_admin = ?, stage = ?,
               tutorial_index = 0, calibration_index = 0, current_sample_id = NULL,
               onboarding_completed_at = NULL WHERE id = ?""",
            (display_name, login_code, is_admin, stage, user_id)
        )
    else:
        db.execute(
            "UPDATE users SET display_name = ?, login_code = ?, is_admin = ?, stage = ? WHERE id = ?",
            (display_name, login_code, is_admin, stage, user_id)
        )
    db.commit()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    return jsonify({"user": {**_user_dict(user), "login_code": user["login_code"]}})


@app.route("/api/admin/samples", methods=["GET"])
@admin_required
def admin_list_samples():
    db = get_db()
    sample_type = request.args.get("sample_type")
    if sample_type:
        samples = db.execute(
            "SELECT * FROM samples WHERE sample_type = ? ORDER BY sort_order, id",
            (sample_type,)
        ).fetchall()
    else:
        samples = db.execute("SELECT * FROM samples ORDER BY sample_type, sort_order, id").fetchall()

    result = []
    for s in samples:
        d = {
            "id": s["id"],
            "sample_type": s["sample_type"],
            "audio_path": s["audio_path"],
            "audio_url": _audio_url(s["audio_path"]),
            "recognized_text": s["recognized_text"],
            "golden_annotation": json.loads(s["golden_annotation"]) if s["golden_annotation"] else None,
            "queue_type": s["queue_type"],
            "is_closed": bool(s["is_closed"]),
            "accepted_annotation_count": s["accepted_annotation_count"],
            "sort_order": s["sort_order"],
        }
        result.append(d)
    db.close()
    return jsonify({"samples": result})


@app.route("/api/admin/samples", methods=["POST"])
@admin_required
def admin_create_sample():
    data = request.get_json(force=True)
    sample_type = data.get("sample_type")
    audio_path = data.get("audio_path", "")
    recognized_text = data.get("recognized_text", "")
    golden = data.get("golden_annotation")
    sort_order = data.get("sort_order", 0)

    if sample_type not in ("tutorial", "calibration", "production"):
        return jsonify({"error": "Invalid sample_type"}), 400

    db = get_db()
    cur = db.execute(
        """INSERT INTO samples (sample_type, audio_path, recognized_text, golden_annotation, sort_order, queue_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sample_type, audio_path, recognized_text,
         json.dumps(golden) if golden else None,
         sort_order,
         "unseen" if sample_type == "production" else None)
    )
    db.commit()
    sample = db.execute("SELECT * FROM samples WHERE id = ?", (cur.lastrowid,)).fetchone()
    db.close()
    return jsonify({"sample": {
        "id": sample["id"],
        "sample_type": sample["sample_type"],
        "audio_path": sample["audio_path"],
    }})


@app.route("/api/admin/samples/<int:sample_id>", methods=["PUT"])
@admin_required
def admin_update_sample(sample_id):
    data = request.get_json(force=True)
    db = get_db()
    sample = db.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
    if not sample:
        db.close()
        return jsonify({"error": "Not found"}), 404

    golden = data.get("golden_annotation")
    recognized_text = data.get("recognized_text", sample["recognized_text"])
    sort_order = data.get("sort_order", sample["sort_order"])
    sample_type = data.get("sample_type", sample["sample_type"])

    db.execute(
        """UPDATE samples SET golden_annotation = ?, recognized_text = ?, sort_order = ?,
           sample_type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
        (json.dumps(golden) if golden else sample["golden_annotation"],
         recognized_text, sort_order, sample_type, sample_id)
    )
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/admin/samples/<int:sample_id>", methods=["DELETE"])
@admin_required
def admin_delete_sample(sample_id):
    db = get_db()
    sample = db.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
    if not sample:
        db.close()
        return jsonify({"error": "Not found"}), 404
    if sample["sample_type"] == "production":
        db.close()
        return jsonify({"error": "Cannot delete production samples"}), 400
    # Remove any annotations for this sample
    db.execute("DELETE FROM annotations WHERE sample_id = ?", (sample_id,))
    db.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/admin/samples/<int:sample_id>/annotations")
@admin_required
def admin_sample_annotations(sample_id):
    db = get_db()
    anns = db.execute("""
        SELECT a.*, u.display_name FROM annotations a
        JOIN users u ON a.user_id = u.id
        WHERE a.sample_id = ?
        ORDER BY a.created_at
    """, (sample_id,)).fetchall()
    db.close()
    return jsonify({"annotations": [
        {
            "id": a["id"],
            "user_id": a["user_id"],
            "display_name": a["display_name"],
            "label": a["label"],
            "annotation_data": json.loads(a["annotation_data"]),
            "status": a["status"],
            "created_at": a["created_at"],
        }
        for a in anns
    ]})


@app.route("/api/admin/queues")
@admin_required
def admin_queue_overview():
    """Return production queue stats and samples with their annotations."""
    db = get_db()
    queue_filter = request.args.get("queue")  # optional: positive, negative, conflict

    # Queue counts
    counts = {}
    for qt in ("unseen", "positive", "negative", "conflict"):
        row = db.execute(
            "SELECT COUNT(*) as c FROM samples WHERE sample_type = 'production' AND queue_type = ? AND is_closed = 0",
            (qt,)
        ).fetchone()
        counts[qt] = row["c"]
    closed_count = db.execute(
        "SELECT COUNT(*) as c FROM samples WHERE sample_type = 'production' AND is_closed = 1"
    ).fetchone()["c"]
    total_count = db.execute(
        "SELECT COUNT(*) as c FROM samples WHERE sample_type = 'production'"
    ).fetchone()["c"]
    counts["closed"] = closed_count
    counts["total"] = total_count

    # If a specific queue is requested, return its samples with annotations
    samples_data = []
    if queue_filter:
        if queue_filter == "closed":
            samples = db.execute(
                "SELECT * FROM samples WHERE sample_type = 'production' AND is_closed = 1 ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        else:
            samples = db.execute(
                "SELECT * FROM samples WHERE sample_type = 'production' AND queue_type = ? AND is_closed = 0 ORDER BY updated_at DESC LIMIT 100",
                (queue_filter,)
            ).fetchall()

        for s in samples:
            anns = db.execute("""
                SELECT a.id, a.user_id, a.label, a.annotation_data, a.status, a.created_at,
                       u.display_name
                FROM annotations a
                JOIN users u ON a.user_id = u.id
                WHERE a.sample_id = ? AND a.status = 'accepted'
                ORDER BY a.created_at
            """, (s["id"],)).fetchall()

            samples_data.append({
                "id": s["id"],
                "audio_url": _audio_url(s["audio_path"]),
                "recognized_text": s["recognized_text"],
                "queue_type": s["queue_type"],
                "is_closed": bool(s["is_closed"]),
                "accepted_annotation_count": s["accepted_annotation_count"],
                "annotations": [
                    {
                        "id": a["id"],
                        "user_id": a["user_id"],
                        "display_name": a["display_name"],
                        "label": a["label"],
                        "annotation_data": json.loads(a["annotation_data"]),
                        "status": a["status"],
                        "created_at": a["created_at"],
                    }
                    for a in anns
                ],
            })

    db.close()
    return jsonify({"counts": counts, "samples": samples_data})


@app.route("/api/admin/samples/pick-for-onboarding", methods=["POST"])
@admin_required
def admin_pick_for_onboarding():
    """Pick production samples that already have accepted annotations and create tutorial/calibration copies with golden annotations derived from those."""
    data = request.get_json(force=True)
    target_type = data.get("sample_type")
    count = data.get("count", 5)

    if target_type not in ("tutorial", "calibration"):
        return jsonify({"error": "sample_type must be tutorial or calibration"}), 400

    db = get_db()

    # Pick closed production samples that have accepted annotations
    # Prefer samples with 2 agreeing annotations (clear consensus)
    candidates = db.execute("""
        SELECT s.*, (
            SELECT a.annotation_data FROM annotations a
            WHERE a.sample_id = s.id AND a.status = 'accepted'
            ORDER BY a.created_at LIMIT 1
        ) AS first_annotation_data,
        (
            SELECT a.label FROM annotations a
            WHERE a.sample_id = s.id AND a.status = 'accepted'
            ORDER BY a.created_at LIMIT 1
        ) AS consensus_label
        FROM samples s
        WHERE s.sample_type = 'production'
          AND s.accepted_annotation_count >= 1
          AND s.id NOT IN (
              SELECT s2.id FROM samples s2
              WHERE s2.sample_type IN ('tutorial', 'calibration')
                AND s2.audio_path = s.audio_path
          )
        ORDER BY s.accepted_annotation_count DESC, RANDOM()
        LIMIT ?
    """, (count,)).fetchall()

    if not candidates:
        db.close()
        return jsonify({"error": "No annotated production samples available. Annotate some production samples first."}), 400

    existing_max_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) as m FROM samples WHERE sample_type = ?",
        (target_type,)
    ).fetchone()["m"]

    created = []
    for i, c in enumerate(candidates):
        # Build golden from the first accepted annotation
        annotation_data = json.loads(c["first_annotation_data"]) if c["first_annotation_data"] else None
        if annotation_data:
            golden = annotation_data  # Use the full annotation payload as golden
        else:
            golden = {"ui_choice": c["consensus_label"] or "negative", "spans": []}

        cur = db.execute(
            """INSERT INTO samples (sample_type, audio_path, recognized_text, sort_order, queue_type, golden_annotation, metadata_json)
               VALUES (?, ?, ?, ?, NULL, ?, ?)""",
            (target_type, c["audio_path"], c["recognized_text"],
             existing_max_order + i + 1, json.dumps(golden), c["metadata_json"])
        )
        created.append({
            "id": cur.lastrowid,
            "audio_path": c["audio_path"],
            "golden_choice": golden.get("ui_choice"),
            "span_count": len(golden.get("spans", [])),
        })

    db.commit()
    db.close()
    return jsonify({"created": created, "count": len(created)})


def auto_export():
    """Automatically write annotations_export.tsv and annotations_export.json to EXPORT_DIR."""
    try:
        db = get_db()
        rows = db.execute("""
            SELECT a.id as annotation_id, a.sample_id, a.user_id, a.label, a.annotation_data,
                   a.status, a.created_at,
                   s.sample_type, s.audio_path, s.recognized_text, s.is_closed,
                   s.accepted_annotation_count, s.queue_type,
                   u.display_name
            FROM annotations a
            JOIN samples s ON a.sample_id = s.id
            JOIN users u ON a.user_id = u.id
            WHERE s.sample_type = 'production'
            ORDER BY s.id, a.created_at
        """).fetchall()
        db.close()

        # TSV
        tsv_path = os.path.join(EXPORT_DIR, "annotations_export.tsv")
        with open(tsv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow([
                "annotation_id", "sample_id", "sample_type", "audio_path", "recognized_text",
                "user_id", "display_name", "label", "ui_choice",
                "span_count", "spans_json", "status",
                "is_closed", "accepted_annotation_count", "queue_type", "created_at"
            ])
            for r in rows:
                ad = json.loads(r["annotation_data"])
                spans = ad.get("spans", [])
                writer.writerow([
                    r["annotation_id"], r["sample_id"], r["sample_type"], r["audio_path"],
                    r["recognized_text"] or "",
                    r["user_id"], r["display_name"], r["label"], ad.get("ui_choice", ""),
                    len(spans), json.dumps(spans, ensure_ascii=False) if spans else "",
                    r["status"], r["is_closed"], r["accepted_annotation_count"],
                    r["queue_type"] or "", r["created_at"]
                ])

        # JSON
        json_path = os.path.join(EXPORT_DIR, "annotations_export.json")
        result = []
        for r in rows:
            ad = json.loads(r["annotation_data"])
            result.append({
                "annotation_id": r["annotation_id"],
                "sample_id": r["sample_id"],
                "sample_type": r["sample_type"],
                "audio_path": r["audio_path"],
                "recognized_text": r["recognized_text"],
                "user_id": r["user_id"],
                "display_name": r["display_name"],
                "label": r["label"],
                "ui_choice": ad.get("ui_choice"),
                "spans": ad.get("spans", []),
                "status": r["status"],
                "is_closed": bool(r["is_closed"]),
                "accepted_annotation_count": r["accepted_annotation_count"],
                "queue_type": r["queue_type"],
                "created_at": r["created_at"],
            })
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        # Auto-export is best-effort; don't break annotation flow
        pass


@app.route("/api/admin/export")
@admin_required
def admin_export():
    """Export all annotations as TSV or JSON."""
    fmt = request.args.get("format", "tsv")
    sample_type = request.args.get("sample_type")  # optional filter

    db = get_db()
    query = """
        SELECT a.id as annotation_id, a.sample_id, a.user_id, a.label, a.annotation_data,
               a.status, a.created_at,
               s.sample_type, s.audio_path, s.recognized_text, s.is_closed,
               s.accepted_annotation_count, s.queue_type,
               u.display_name
        FROM annotations a
        JOIN samples s ON a.sample_id = s.id
        JOIN users u ON a.user_id = u.id
    """
    params = []
    if sample_type:
        query += " WHERE s.sample_type = ?"
        params.append(sample_type)
    query += " ORDER BY s.id, a.created_at"

    rows = db.execute(query, params).fetchall()
    db.close()

    if fmt == "json":
        result = []
        for r in rows:
            ad = json.loads(r["annotation_data"])
            result.append({
                "annotation_id": r["annotation_id"],
                "sample_id": r["sample_id"],
                "sample_type": r["sample_type"],
                "audio_path": r["audio_path"],
                "recognized_text": r["recognized_text"],
                "user_id": r["user_id"],
                "display_name": r["display_name"],
                "label": r["label"],
                "ui_choice": ad.get("ui_choice"),
                "spans": ad.get("spans", []),
                "status": r["status"],
                "is_closed": bool(r["is_closed"]),
                "accepted_annotation_count": r["accepted_annotation_count"],
                "queue_type": r["queue_type"],
                "created_at": r["created_at"],
            })
        return Response(
            json.dumps(result, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=annotations_export.json"}
        )

    # Default: TSV
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t")
    writer.writerow([
        "annotation_id", "sample_id", "sample_type", "audio_path", "recognized_text",
        "user_id", "display_name", "label", "ui_choice",
        "span_count", "spans_json", "status",
        "is_closed", "accepted_annotation_count", "queue_type", "created_at"
    ])
    for r in rows:
        ad = json.loads(r["annotation_data"])
        spans = ad.get("spans", [])
        writer.writerow([
            r["annotation_id"], r["sample_id"], r["sample_type"], r["audio_path"],
            r["recognized_text"] or "",
            r["user_id"], r["display_name"], r["label"], ad.get("ui_choice", ""),
            len(spans), json.dumps(spans, ensure_ascii=False) if spans else "",
            r["status"], r["is_closed"], r["accepted_annotation_count"],
            r["queue_type"] or "", r["created_at"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/tab-separated-values",
        headers={"Content-Disposition": "attachment; filename=annotations_export.tsv"}
    )


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)
