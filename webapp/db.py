import sqlite3
import os

DB_PATH = os.environ.get("ANNOTATION_DB", os.path.join(os.path.dirname(__file__), "..", "annotations.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login_code TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        current_sample_id INTEGER,
        stage TEXT NOT NULL DEFAULT 'rules',
        tutorial_index INTEGER NOT NULL DEFAULT 0,
        calibration_index INTEGER NOT NULL DEFAULT 0,
        onboarding_completed_at TIMESTAMP,
        FOREIGN KEY (current_sample_id) REFERENCES samples(id)
    );

    CREATE TABLE IF NOT EXISTS samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sample_type TEXT NOT NULL CHECK(sample_type IN ('tutorial', 'calibration', 'production')),
        audio_path TEXT NOT NULL,
        recognized_text TEXT,
        golden_annotation TEXT,
        queue_type TEXT DEFAULT 'unseen' CHECK(queue_type IN ('unseen', 'negative', 'positive', 'conflict')),
        is_closed INTEGER NOT NULL DEFAULT 0,
        accepted_annotation_count INTEGER NOT NULL DEFAULT 0,
        sort_order INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS annotations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sample_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        label TEXT NOT NULL CHECK(label IN ('negative', 'positive')),
        annotation_data TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'accepted' CHECK(status IN ('accepted', 'overdone')),
        UNIQUE(sample_id, user_id),
        FOREIGN KEY (sample_id) REFERENCES samples(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE INDEX IF NOT EXISTS idx_samples_queue ON samples(sample_type, queue_type, is_closed);
    CREATE INDEX IF NOT EXISTS idx_annotations_sample ON annotations(sample_id);
    CREATE INDEX IF NOT EXISTS idx_annotations_user ON annotations(user_id);
    """)
    conn.commit()
    conn.close()
