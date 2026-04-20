"""Unit tests for the overlap annotation web app."""

import json
import os
import tempfile

import pytest

# Point DB and audio dir to temp locations before importing app
_tmpdir = tempfile.mkdtemp()
os.environ["ANNOTATION_DB"] = os.path.join(_tmpdir, "test.db")

from webapp.app import app
from webapp.db import get_db, init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Give each test a fresh SQLite database."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("webapp.db.DB_PATH", db_path)
    init_db()
    yield db_path


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(login_code="user1", display_name="Test User", is_admin=False, stage="rules"):
    db = get_db()
    db.execute(
        "INSERT INTO users (login_code, display_name, is_admin, stage) VALUES (?, ?, ?, ?)",
        (login_code, display_name, int(is_admin), stage),
    )
    db.commit()
    uid = db.execute("SELECT id FROM users WHERE login_code = ?", (login_code,)).fetchone()["id"]
    db.close()
    return uid


def _create_sample(sample_type="production", audio_path="test.wav", recognized_text="hello",
                   golden_annotation=None, sort_order=0, queue_type="unseen"):
    db = get_db()
    db.execute(
        """INSERT INTO samples (sample_type, audio_path, recognized_text, golden_annotation,
           sort_order, queue_type) VALUES (?, ?, ?, ?, ?, ?)""",
        (sample_type, audio_path, recognized_text,
         json.dumps(golden_annotation) if golden_annotation else None,
         sort_order, queue_type if sample_type == "production" else None),
    )
    db.commit()
    sid = db.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    db.close()
    return sid


def _login(client, login_code="user1"):
    return client.post("/api/login", json={"login_code": login_code})


def _annotation_data(ui_choice="negative", spans=None):
    return {"ui_choice": ui_choice, "spans": spans or []}


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    def test_login_success(self, client):
        _create_user()
        resp = _login(client)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["display_name"] == "Test User"
        assert data["user"]["stage"] == "rules"

    def test_login_invalid_code(self, client):
        resp = client.post("/api/login", json={"login_code": "nope"})
        assert resp.status_code == 401

    def test_login_empty_code(self, client):
        resp = client.post("/api/login", json={"login_code": ""})
        assert resp.status_code == 400

    def test_login_missing_code(self, client):
        resp = client.post("/api/login", json={})
        assert resp.status_code == 400

    def test_logout(self, client):
        _create_user()
        _login(client)
        resp = client.post("/api/logout")
        assert resp.status_code == 200
        # After logout, /api/me should fail
        resp = client.get("/api/me")
        assert resp.status_code == 401

    def test_me_authenticated(self, client):
        _create_user()
        _login(client)
        resp = client.get("/api/me")
        assert resp.status_code == 200
        assert resp.get_json()["user"]["display_name"] == "Test User"

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/me")
        assert resp.status_code == 401

    def test_login_required_decorator(self, client):
        resp = client.get("/api/task/current")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Task flow: rules → tutorial → calibration → production
# ---------------------------------------------------------------------------

class TestTaskFlow:
    def test_rules_stage(self, client):
        _create_user(stage="rules")
        _login(client)
        resp = client.get("/api/task/current")
        assert resp.get_json()["mode"] == "rules"

    def test_acknowledge_rules(self, client):
        _create_user(stage="rules")
        _login(client)
        resp = client.post("/api/rules/acknowledge")
        assert resp.status_code == 200
        # Stage should now be 'tutorial'
        resp = client.get("/api/me")
        assert resp.get_json()["user"]["stage"] == "tutorial"

    def test_acknowledge_rules_idempotent(self, client):
        _create_user(stage="tutorial")
        _login(client)
        resp = client.post("/api/rules/acknowledge")
        assert resp.status_code == 200

    def test_tutorial_task(self, client):
        _create_user(stage="tutorial")
        golden = {"ui_choice": "negative", "spans": []}
        _create_sample("tutorial", golden_annotation=golden, sort_order=0)
        _login(client)
        resp = client.get("/api/task/current")
        data = resp.get_json()
        assert data["mode"] == "tutorial"
        assert data["index"] == 0
        assert data["total"] == 1

    def test_tutorial_submit_advances(self, client):
        uid = _create_user(stage="tutorial")
        golden = {"ui_choice": "negative", "spans": []}
        sid = _create_sample("tutorial", golden_annotation=golden)
        _login(client)
        resp = client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("negative"),
        })
        data = resp.get_json()
        assert data["result"] == "accepted"
        assert data["feedback"] == golden
        # With only one tutorial sample, user advances to calibration
        assert data["stage"] == "calibration"

    def test_tutorial_submit_duplicate(self, client):
        _create_user(stage="tutorial")
        golden = {"ui_choice": "negative", "spans": []}
        sid = _create_sample("tutorial", golden_annotation=golden)
        _login(client)
        client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("negative"),
        })
        resp = client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("negative"),
        })
        assert resp.status_code == 409

    def test_tutorial_auto_advance_to_calibration(self, client):
        """When no tutorial samples exist, user goes straight to calibration."""
        _create_user(stage="tutorial")
        _login(client)
        resp = client.get("/api/task/current")
        data = resp.get_json()
        # No tutorials → should fall through to calibration
        # No calibrations either → should fall through to production
        assert data["mode"] == "production"

    def test_calibration_task(self, client):
        _create_user(stage="calibration")
        golden = {"ui_choice": "positive_localizable", "spans": [{"start": 0, "end": 1}]}
        _create_sample("calibration", golden_annotation=golden)
        _login(client)
        resp = client.get("/api/task/current")
        data = resp.get_json()
        assert data["mode"] == "calibration"
        assert data["total"] == 1

    def test_calibration_submit_last_returns_results(self, client):
        _create_user(stage="calibration")
        golden = {"ui_choice": "negative", "spans": []}
        sid = _create_sample("calibration", golden_annotation=golden)
        _login(client)
        resp = client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("negative"),
        })
        data = resp.get_json()
        assert data["result"] == "accepted"
        assert data["stage"] == "production"
        assert "calibration_results" in data
        assert len(data["calibration_results"]) == 1

    def test_calibration_results_endpoint(self, client):
        _create_user(stage="calibration")
        golden = {"ui_choice": "negative", "spans": []}
        sid = _create_sample("calibration", golden_annotation=golden)
        _login(client)
        # Submit first
        client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("negative"),
        })
        resp = client.get("/api/calibration/results")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["results"]) == 1
        assert data["results"][0]["golden"] == golden

    def test_no_samples_available(self, client):
        _create_user(stage="production")
        _login(client)
        resp = client.get("/api/task/current")
        data = resp.get_json()
        assert data["mode"] == "production"
        assert data["sample"] is None


# ---------------------------------------------------------------------------
# Production submit & queue logic
# ---------------------------------------------------------------------------

class TestProductionSubmit:
    def _setup_production(self, client, num_samples=1, queue_type="unseen"):
        uid = _create_user(stage="production")
        sids = []
        for i in range(num_samples):
            sids.append(_create_sample("production", audio_path=f"test{i}.wav", queue_type=queue_type))
        _login(client)
        return uid, sids

    def test_production_task_assignment(self, client):
        uid, sids = self._setup_production(client)
        resp = client.get("/api/task/current")
        data = resp.get_json()
        assert data["mode"] == "production"
        assert data["sample"]["id"] == sids[0]

    def test_production_submit_accepted(self, client, monkeypatch):
        # Patch auto_export to avoid file writes and git calls
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        uid, sids = self._setup_production(client)
        # Get task to assign sample
        client.get("/api/task/current")
        resp = client.post("/api/task/submit", json={
            "sample_id": sids[0],
            "annotation_data": _annotation_data("positive_localizable", [{"start": 0, "end": 1}]),
        })
        assert resp.status_code == 200
        assert resp.get_json()["result"] == "accepted"

    def test_production_submit_duplicate(self, client, monkeypatch):
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        uid, sids = self._setup_production(client)
        client.get("/api/task/current")
        client.post("/api/task/submit", json={
            "sample_id": sids[0],
            "annotation_data": _annotation_data("negative"),
        })
        resp = client.post("/api/task/submit", json={
            "sample_id": sids[0],
            "annotation_data": _annotation_data("negative"),
        })
        assert resp.status_code == 409
        assert resp.get_json()["result"] == "duplicate"

    def test_production_positive_routes_to_positive_queue(self, client, monkeypatch):
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        uid, sids = self._setup_production(client)
        client.get("/api/task/current")
        client.post("/api/task/submit", json={
            "sample_id": sids[0],
            "annotation_data": _annotation_data("positive_localizable", [{"start": 0.1, "end": 0.5}]),
        })
        db = get_db()
        sample = db.execute("SELECT * FROM samples WHERE id = ?", (sids[0],)).fetchone()
        db.close()
        assert sample["queue_type"] == "positive"
        assert not sample["is_closed"]

    def test_production_negative_closes_90pct(self, client, monkeypatch):
        """With random < NEGATIVE_REQUEUE_PROB threshold, negative requeues."""
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        # Force random to return 0.5 (> 0.1 threshold) → should close
        monkeypatch.setattr("webapp.app.random.random", lambda: 0.5)
        uid, sids = self._setup_production(client)
        client.get("/api/task/current")
        client.post("/api/task/submit", json={
            "sample_id": sids[0],
            "annotation_data": _annotation_data("negative"),
        })
        db = get_db()
        sample = db.execute("SELECT * FROM samples WHERE id = ?", (sids[0],)).fetchone()
        db.close()
        assert sample["is_closed"] == 1

    def test_production_negative_requeues_10pct(self, client, monkeypatch):
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        # Force random to return 0.05 (< 0.1 threshold) → should requeue to negative
        monkeypatch.setattr("webapp.app.random.random", lambda: 0.05)
        uid, sids = self._setup_production(client)
        client.get("/api/task/current")
        client.post("/api/task/submit", json={
            "sample_id": sids[0],
            "annotation_data": _annotation_data("negative"),
        })
        db = get_db()
        sample = db.execute("SELECT * FROM samples WHERE id = ?", (sids[0],)).fetchone()
        db.close()
        assert sample["queue_type"] == "negative"
        assert not sample["is_closed"]

    def test_two_agreeing_annotations_close(self, client, monkeypatch):
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        # User 1 annotates positive
        _create_user("u1", "User1", stage="production")
        _create_user("u2", "User2", stage="production")
        sid = _create_sample("production")
        _login(client, "u1")
        client.get("/api/task/current")
        client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("positive_localizable", [{"start": 0, "end": 1}]),
        })
        # User 2 also annotates positive
        _login(client, "u2")
        # Manually assign the sample
        db = get_db()
        db.execute("UPDATE users SET current_sample_id = ? WHERE login_code = 'u2'", (sid,))
        db.commit()
        db.close()
        client.get("/api/task/current")
        client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("positive_not_localizable"),
        })
        db = get_db()
        sample = db.execute("SELECT * FROM samples WHERE id = ?", (sid,)).fetchone()
        db.close()
        assert sample["is_closed"] == 1
        assert sample["accepted_annotation_count"] == 2

    def test_disagreement_marks_conflict(self, client, monkeypatch):
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        _create_user("u1", "User1", stage="production")
        _create_user("u2", "User2", stage="production")
        sid = _create_sample("production")
        # User 1: positive
        _login(client, "u1")
        client.get("/api/task/current")
        client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("positive_localizable", [{"start": 0, "end": 1}]),
        })
        # User 2: negative
        _login(client, "u2")
        db = get_db()
        db.execute("UPDATE users SET current_sample_id = ? WHERE login_code = 'u2'", (sid,))
        db.commit()
        db.close()
        client.get("/api/task/current")
        client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("negative"),
        })
        db = get_db()
        sample = db.execute("SELECT * FROM samples WHERE id = ?", (sid,)).fetchone()
        db.close()
        assert sample["queue_type"] == "conflict"
        assert not sample["is_closed"]

    def test_three_annotations_always_close(self, client, monkeypatch):
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        _create_user("u1", "User1", stage="production")
        _create_user("u2", "User2", stage="production")
        _create_user("u3", "User3", stage="production")
        sid = _create_sample("production")

        for code, choice in [("u1", "positive_localizable"), ("u2", "negative"), ("u3", "positive_localizable")]:
            _login(client, code)
            db = get_db()
            db.execute(f"UPDATE users SET current_sample_id = ? WHERE login_code = ?", (sid, code))
            db.commit()
            db.close()
            client.get("/api/task/current")
            spans = [{"start": 0, "end": 1}] if "positive" in choice else []
            client.post("/api/task/submit", json={
                "sample_id": sid,
                "annotation_data": _annotation_data(choice, spans),
            })

        db = get_db()
        sample = db.execute("SELECT * FROM samples WHERE id = ?", (sid,)).fetchone()
        db.close()
        assert sample["is_closed"] == 1
        assert sample["accepted_annotation_count"] == 3

    def test_overdone_after_close(self, client, monkeypatch):
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        _create_user("u1", "User1", stage="production")
        _create_user("late", "Late User", stage="production")
        sid = _create_sample("production")

        # Close the sample by making two agreeing annotations
        _create_user("u2", "User2", stage="production")
        for code in ("u1", "u2"):
            _login(client, code)
            db = get_db()
            db.execute("UPDATE users SET current_sample_id = ? WHERE login_code = ?", (sid, code))
            db.commit()
            db.close()
            client.get("/api/task/current")
            client.post("/api/task/submit", json={
                "sample_id": sid,
                "annotation_data": _annotation_data("positive_localizable", [{"start": 0, "end": 1}]),
            })

        # Late user tries to submit to the now-closed sample
        _login(client, "late")
        db = get_db()
        db.execute("UPDATE users SET current_sample_id = ? WHERE login_code = 'late'", (sid,))
        db.commit()
        db.close()
        resp = client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": _annotation_data("negative"),
        })
        assert resp.get_json()["result"] == "overdone"

    def test_submit_missing_data(self, client):
        _create_user(stage="production")
        _login(client)
        resp = client.post("/api/task/submit", json={"sample_id": 1})
        assert resp.status_code == 400

    def test_submit_invalid_ui_choice(self, client):
        _create_user(stage="production")
        sid = _create_sample("production")
        _login(client)
        resp = client.post("/api/task/submit", json={
            "sample_id": sid,
            "annotation_data": {"ui_choice": "invalid", "spans": []},
        })
        assert resp.status_code == 400

    def test_submit_sample_not_found(self, client):
        _create_user(stage="production")
        _login(client)
        resp = client.post("/api/task/submit", json={
            "sample_id": 9999,
            "annotation_data": _annotation_data("negative"),
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Queue selection logic
# ---------------------------------------------------------------------------

class TestQueueSelection:
    def test_conflict_queue_prioritized(self, client, monkeypatch):
        monkeypatch.setattr("webapp.app.auto_export", lambda: None)
        _create_user(stage="production")
        # Create one unseen and one conflict sample
        _create_sample("production", audio_path="unseen.wav", queue_type="unseen")
        conflict_sid = _create_sample("production", audio_path="conflict.wav", queue_type="conflict")
        _login(client)
        resp = client.get("/api/task/current")
        # Should pick from conflict queue first
        assert resp.get_json()["sample"]["id"] == conflict_sid

    def test_stale_assignment_cleared(self, client):
        """If a user's assigned sample is closed, they get a new one."""
        uid = _create_user(stage="production")
        sid = _create_sample("production")
        # Close the sample
        db = get_db()
        db.execute("UPDATE samples SET is_closed = 1 WHERE id = ?", (sid,))
        db.execute("UPDATE users SET current_sample_id = ? WHERE id = ?", (sid, uid))
        db.commit()
        db.close()
        _login(client)
        resp = client.get("/api/task/current")
        data = resp.get_json()
        # Should not return the closed sample
        assert data["sample"] is None or data["sample"]["id"] != sid


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

class TestAdmin:
    def _setup_admin(self, client):
        _create_user("admin1", "Admin", is_admin=True, stage="production")
        _login(client, "admin1")

    def test_admin_required(self, client):
        _create_user(stage="production")
        _login(client)
        resp = client.get("/api/admin/users")
        assert resp.status_code == 403

    def test_admin_list_users(self, client):
        self._setup_admin(client)
        resp = client.get("/api/admin/users")
        assert resp.status_code == 200
        users = resp.get_json()["users"]
        assert len(users) >= 1
        assert "login_code" in users[0]

    def test_admin_create_user(self, client):
        self._setup_admin(client)
        resp = client.post("/api/admin/users", json={
            "display_name": "New User",
            "login_code": "newcode",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["display_name"] == "New User"
        assert data["user"]["login_code"] == "newcode"

    def test_admin_create_user_auto_code(self, client):
        self._setup_admin(client)
        resp = client.post("/api/admin/users", json={"display_name": "Auto"})
        assert resp.status_code == 200
        assert len(resp.get_json()["user"]["login_code"]) == 8  # token_hex(4)

    def test_admin_create_user_empty_name(self, client):
        self._setup_admin(client)
        resp = client.post("/api/admin/users", json={"display_name": ""})
        assert resp.status_code == 400

    def test_admin_create_user_duplicate_code(self, client):
        self._setup_admin(client)
        client.post("/api/admin/users", json={"display_name": "A", "login_code": "dup"})
        resp = client.post("/api/admin/users", json={"display_name": "B", "login_code": "dup"})
        assert resp.status_code == 400

    def test_admin_update_user(self, client):
        self._setup_admin(client)
        uid = _create_user("target", "Target")
        resp = client.put(f"/api/admin/users/{uid}", json={"display_name": "Updated"})
        assert resp.status_code == 200
        assert resp.get_json()["user"]["display_name"] == "Updated"

    def test_admin_update_user_not_found(self, client):
        self._setup_admin(client)
        resp = client.put("/api/admin/users/9999", json={"display_name": "X"})
        assert resp.status_code == 404

    def test_admin_reset_user_stage(self, client):
        self._setup_admin(client)
        uid = _create_user("target", "Target", stage="production")
        # Create a tutorial sample with annotation
        golden = {"ui_choice": "negative", "spans": []}
        sid = _create_sample("tutorial", golden_annotation=golden)
        db = get_db()
        db.execute(
            "INSERT INTO annotations (sample_id, user_id, label, annotation_data) VALUES (?, ?, 'negative', '{}')",
            (sid, uid),
        )
        db.commit()
        db.close()
        # Reset user to tutorial
        resp = client.put(f"/api/admin/users/{uid}", json={"stage": "tutorial"})
        assert resp.status_code == 200
        user = resp.get_json()["user"]
        assert user["stage"] == "tutorial"
        assert user["tutorial_index"] == 0
        # Old annotation should be deleted
        db = get_db()
        ann = db.execute("SELECT * FROM annotations WHERE user_id = ? AND sample_id = ?", (uid, sid)).fetchone()
        db.close()
        assert ann is None

    def test_admin_create_sample(self, client):
        self._setup_admin(client)
        resp = client.post("/api/admin/samples", json={
            "sample_type": "tutorial",
            "audio_path": "test.wav",
            "recognized_text": "hello",
        })
        assert resp.status_code == 200
        assert resp.get_json()["sample"]["sample_type"] == "tutorial"

    def test_admin_create_sample_invalid_type(self, client):
        self._setup_admin(client)
        resp = client.post("/api/admin/samples", json={
            "sample_type": "invalid",
            "audio_path": "x.wav",
        })
        assert resp.status_code == 400

    def test_admin_list_samples(self, client):
        self._setup_admin(client)
        _create_sample("production")
        resp = client.get("/api/admin/samples")
        assert resp.status_code == 200
        assert len(resp.get_json()["samples"]) >= 1

    def test_admin_list_samples_filter(self, client):
        self._setup_admin(client)
        _create_sample("tutorial")
        _create_sample("production")
        resp = client.get("/api/admin/samples?sample_type=tutorial")
        samples = resp.get_json()["samples"]
        assert all(s["sample_type"] == "tutorial" for s in samples)

    def test_admin_update_sample(self, client):
        self._setup_admin(client)
        sid = _create_sample("tutorial")
        resp = client.put(f"/api/admin/samples/{sid}", json={
            "recognized_text": "updated",
        })
        assert resp.status_code == 200

    def test_admin_update_sample_not_found(self, client):
        self._setup_admin(client)
        resp = client.put("/api/admin/samples/9999", json={"recognized_text": "x"})
        assert resp.status_code == 404

    def test_admin_delete_tutorial_sample(self, client):
        self._setup_admin(client)
        sid = _create_sample("tutorial")
        resp = client.delete(f"/api/admin/samples/{sid}")
        assert resp.status_code == 200

    def test_admin_cannot_delete_production_sample(self, client):
        self._setup_admin(client)
        sid = _create_sample("production")
        resp = client.delete(f"/api/admin/samples/{sid}")
        assert resp.status_code == 400

    def test_admin_sample_annotations(self, client):
        self._setup_admin(client)
        uid = _create_user("auser", "A User")
        sid = _create_sample("production")
        db = get_db()
        db.execute(
            "INSERT INTO annotations (sample_id, user_id, label, annotation_data) VALUES (?, ?, 'positive', ?)",
            (sid, uid, json.dumps({"ui_choice": "positive_localizable", "spans": []})),
        )
        db.commit()
        db.close()
        resp = client.get(f"/api/admin/samples/{sid}/annotations")
        assert resp.status_code == 200
        anns = resp.get_json()["annotations"]
        assert len(anns) == 1
        assert anns[0]["display_name"] == "A User"

    def test_admin_queue_overview(self, client):
        self._setup_admin(client)
        _create_sample("production", queue_type="unseen")
        _create_sample("production", audio_path="p.wav", queue_type="positive")
        resp = client.get("/api/admin/queues")
        assert resp.status_code == 200
        counts = resp.get_json()["counts"]
        assert counts["unseen"] >= 1
        assert counts["positive"] >= 1

    def test_admin_queue_overview_with_filter(self, client):
        self._setup_admin(client)
        _create_sample("production", queue_type="positive")
        resp = client.get("/api/admin/queues?queue=positive")
        data = resp.get_json()
        assert len(data["samples"]) >= 1

    def test_admin_pick_for_onboarding(self, client):
        self._setup_admin(client)
        sid = _create_sample("production")
        uid = _create_user("ann", "Annotator", stage="production")
        db = get_db()
        db.execute(
            "INSERT INTO annotations (sample_id, user_id, label, annotation_data, status) VALUES (?, ?, 'positive', ?, 'accepted')",
            (sid, uid, json.dumps({"ui_choice": "positive_localizable", "spans": []})),
        )
        db.execute("UPDATE samples SET accepted_annotation_count = 1 WHERE id = ?", (sid,))
        db.commit()
        db.close()
        resp = client.post("/api/admin/samples/pick-for-onboarding", json={
            "sample_type": "tutorial",
            "count": 1,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1

    def test_admin_pick_for_onboarding_invalid_type(self, client):
        self._setup_admin(client)
        resp = client.post("/api/admin/samples/pick-for-onboarding", json={
            "sample_type": "production",
            "count": 1,
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_admin_export_tsv(self, client):
        _create_user("admin1", "Admin", is_admin=True, stage="production")
        _login(client, "admin1")
        resp = client.get("/api/admin/export?format=tsv")
        assert resp.status_code == 200
        assert "text/tab-separated-values" in resp.content_type

    def test_admin_export_json(self, client):
        _create_user("admin1", "Admin", is_admin=True, stage="production")
        _login(client, "admin1")
        resp = client.get("/api/admin/export?format=json")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type

    def test_admin_export_with_filter(self, client):
        _create_user("admin1", "Admin", is_admin=True, stage="production")
        _login(client, "admin1")
        resp = client.get("/api/admin/export?format=json&sample_type=production")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Database init
# ---------------------------------------------------------------------------

class TestDatabase:
    def test_init_db_creates_tables(self):
        db = get_db()
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        db.close()
        table_names = {t["name"] for t in tables}
        assert "users" in table_names
        assert "samples" in table_names
        assert "annotations" in table_names

    def test_init_db_idempotent(self):
        init_db()
        init_db()  # Should not raise
        db = get_db()
        count = db.execute("SELECT COUNT(*) as c FROM sqlite_master WHERE type='table'").fetchone()["c"]
        db.close()
        assert count >= 3

    def test_wal_mode(self):
        db = get_db()
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        db.close()
        assert mode == "wal"

    def test_foreign_keys_enabled(self):
        db = get_db()
        fk = db.execute("PRAGMA foreign_keys").fetchone()[0]
        db.close()
        assert fk == 1
