"""tests/test_database.py — SQLite layer unit tests using :memory: database."""
import importlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        import config.settings as s
        self._orig = s.DB_PATH
        s.DB_PATH = self.tmp.name
        import src.database as dbm
        importlib.reload(dbm)
        dbm.init_db()
        self.db = dbm

    def tearDown(self):
        import config.settings as s
        s.DB_PATH = self._orig
        os.unlink(self.tmp.name)

    def _save_test_email(self, gid="test-001"):
        return self.db.save_email({
            "gmail_message_id": gid,
            "sender":    "test@example.com",
            "subject":   "Test Email",
            "received_at": "Mon, 01 Apr 2025 10:00:00 +0000",
            "body_hash": "abc123",
        })

    def _future(self, days=10):
        return datetime.now() + timedelta(days=days)

    # ── Email ──────────────────────────────────────────────────────────────────

    def test_save_email_returns_id(self):
        eid = self._save_test_email()
        self.assertGreater(eid, 0)

    def test_email_exists_true(self):
        self._save_test_email("gid-001")
        self.assertTrue(self.db.email_exists("gid-001"))

    def test_email_exists_false(self):
        self.assertFalse(self.db.email_exists("nonexistent"))

    def test_duplicate_email_returns_same_id(self):
        id1 = self._save_test_email("dup-001")
        id2 = self._save_test_email("dup-001")
        self.assertEqual(id1, id2)

    # ── Deadlines ─────────────────────────────────────────────────────────────

    def test_save_deadline_returns_id(self):
        eid = self._save_test_email()
        did = self.db.save_deadline({
            "email_id":      eid,
            "action_type":   "payment_due",
            "source_phrase": "Pay by next month",
            "deadline_at":   self._future(10),
            "remind_at":     self._future(9),
            "confidence":    0.9,
            "detected_by":   "rule",
        })
        self.assertGreater(did, 0)

    def test_get_all_pending_returns_saved(self):
        eid = self._save_test_email()
        self.db.save_deadline({
            "email_id":    eid, "action_type": "reply_deadline",
            "source_phrase": "Reply by Friday",
            "deadline_at": self._future(5), "remind_at": self._future(4),
            "confidence":  0.85, "detected_by": "rule",
        })
        rows = self.db.get_all_pending()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_type"], "reply_deadline")

    def test_deadline_exists_check(self):
        eid = self._save_test_email()
        self.db.save_deadline({
            "email_id":    eid, "action_type": "payment_due",
            "source_phrase": "Pay by April",
            "deadline_at": self._future(7), "remind_at": self._future(6),
            "confidence": 0.9, "detected_by": "rule",
        })
        self.assertTrue(self.db.deadline_exists(eid, "payment_due"))
        self.assertFalse(self.db.deadline_exists(eid, "reply_deadline"))

    def test_get_due_reminders_returns_past_remind(self):
        eid = self._save_test_email()
        self.db.save_deadline({
            "email_id":    eid, "action_type": "submission_deadline",
            "source_phrase": "Submit by next week",
            "deadline_at": self._future(5),
            "remind_at":   datetime.now() - timedelta(hours=1),   # in the past
            "confidence": 0.88, "detected_by": "rule",
        })
        due = self.db.get_due_reminders()
        self.assertEqual(len(due), 1)

    def test_get_due_reminders_empty_for_future_remind(self):
        eid = self._save_test_email()
        self.db.save_deadline({
            "email_id":    eid, "action_type": "payment_due",
            "source_phrase": "Pay by April",
            "deadline_at": self._future(10),
            "remind_at":   self._future(9),   # still in the future
            "confidence": 0.9, "detected_by": "rule",
        })
        self.assertEqual(len(self.db.get_due_reminders()), 0)

    def test_mark_reminded_changes_status(self):
        eid = self._save_test_email()
        did = self.db.save_deadline({
            "email_id":    eid, "action_type": "payment_due",
            "source_phrase": "Pay now",
            "deadline_at": self._future(5),
            "remind_at":   datetime.now() - timedelta(hours=1),
            "confidence": 0.9, "detected_by": "rule",
        })
        self.db.mark_reminded(did)
        rows = self.db.get_all_pending()
        self.assertEqual(len(rows), 0)

    def test_snooze_hides_from_due(self):
        eid = self._save_test_email()
        did = self.db.save_deadline({
            "email_id":    eid, "action_type": "reply_deadline",
            "source_phrase": "Reply ASAP",
            "deadline_at": self._future(3),
            "remind_at":   datetime.now() - timedelta(hours=1),
            "confidence": 0.85, "detected_by": "rule",
        })
        future = (datetime.now() + timedelta(hours=24)).isoformat()
        self.db.snooze_dl(did, future)
        self.assertEqual(len(self.db.get_due_reminders()), 0)

    def test_dismiss_removes_from_pending(self):
        eid = self._save_test_email()
        did = self.db.save_deadline({
            "email_id":    eid, "action_type": "payment_due",
            "source_phrase": "Pay by Friday",
            "deadline_at": self._future(5),
            "remind_at":   self._future(4),
            "confidence": 0.9, "detected_by": "rule",
        })
        self.db.dismiss_dl(did)
        self.assertEqual(len(self.db.get_all_pending()), 0)

    # ── Agent memory ───────────────────────────────────────────────────────────

    def test_add_and_get_memory(self):
        self.db.add_memory("sess1", "user", "Find deadlines")
        self.db.add_memory("sess1", "assistant", "Found 2 deadlines")
        mem = self.db.get_memory("sess1")
        self.assertEqual(len(mem), 2)
        self.assertEqual(mem[0]["role"], "user")
        self.assertEqual(mem[1]["content"], "Found 2 deadlines")

    def test_memory_isolation_by_session(self):
        self.db.add_memory("sess-A", "user", "Task A")
        self.db.add_memory("sess-B", "user", "Task B")
        self.assertEqual(len(self.db.get_memory("sess-A")), 1)
        self.assertEqual(len(self.db.get_memory("sess-B")), 1)

    def test_clear_memory(self):
        self.db.add_memory("sess2", "user", "Hello")
        self.db.clear_memory("sess2")
        self.assertEqual(len(self.db.get_memory("sess2")), 0)

    # ── body_hash ──────────────────────────────────────────────────────────────

    def test_body_hash_consistent(self):
        h1 = self.db.body_hash("Hello world")
        h2 = self.db.body_hash("Hello world")
        self.assertEqual(h1, h2)

    def test_body_hash_differs(self):
        self.assertNotEqual(
            self.db.body_hash("text one"),
            self.db.body_hash("text two")
        )


if __name__ == "__main__":
    unittest.main()
