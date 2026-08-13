from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._helper_loader import SKILL_ROOT, helper


class SQLiteBackupTests(unittest.TestCase):
    def test_snapshot_includes_committed_rows_still_in_the_live_wal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-wal-") as td:
            source = Path(td) / "chat.db"
            with sqlite3.connect(str(source)) as writer:
                self.assertEqual(
                    writer.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",)
                )
                writer.execute("PRAGMA wal_autocheckpoint=0")
                writer.execute("CREATE TABLE sample(value TEXT)")
                writer.commit()
                writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                writer.execute("INSERT INTO sample VALUES ('from-live-wal')")
                writer.commit()
                self.assertGreater(Path(f"{source}-wal").stat().st_size, 0)

                with mock.patch.object(helper, "CHAT_DB_PATH", source):
                    snapshot = helper.copy_chatdb()
                self.addCleanup(helper.cleanup_tmpdb, snapshot)

            with sqlite3.connect(str(snapshot)) as reader:
                self.assertEqual(
                    reader.execute("SELECT value FROM sample").fetchall(),
                    [("from-live-wal",)],
                )
                self.assertEqual(
                    reader.execute("PRAGMA integrity_check").fetchone(), ("ok",)
                )

    def test_production_open_reads_wal_snapshot_without_sidecars(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-wal-open-") as td:
            source = Path(td) / "chat.db"
            with sqlite3.connect(str(source)) as writer:
                self.assertEqual(
                    writer.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",)
                )
                writer.execute("CREATE TABLE sample(value TEXT)")
                writer.execute("INSERT INTO sample VALUES ('wal-header')")
                writer.commit()

                with mock.patch.object(helper, "CHAT_DB_PATH", source):
                    snapshot = helper.copy_chatdb()
                self.addCleanup(helper.cleanup_tmpdb, snapshot)

            wal_path = Path(f"{snapshot}-wal")
            shm_path = Path(f"{snapshot}-shm")
            self.assertEqual(snapshot.read_bytes()[18:20], b"\x02\x02")
            self.assertFalse(wal_path.exists())
            self.assertFalse(shm_path.exists())

            with helper.open_snapshot(snapshot) as reader:
                self.assertEqual(
                    reader.execute("SELECT value FROM sample").fetchall(),
                    [(b"wal-header",)],
                )
                self.assertFalse(wal_path.exists())
                self.assertFalse(shm_path.exists())


class StatusAndQueueTests(unittest.TestCase):
    def _runtime(self, root: Path) -> tuple[Path, Path, Path, Path]:
        bridge = Path(os.path.realpath(root))
        bridge.chmod(0o700)
        control = bridge / "control"
        requests = control / "requests"
        responses = control / "responses"
        for directory in (control, requests, responses):
            directory.mkdir(mode=0o700)
        log = control / "log.txt"
        log.write_text("")
        log.chmod(0o600)
        return bridge, requests, responses, log

    def test_status_is_host_specific_and_reads_no_private_database(self) -> None:
        self.assertFalse(helper.action_status.needs_db)
        self.assertFalse(helper.action_status.needs_contacts)
        with tempfile.TemporaryDirectory(prefix="claude-imessage-status-") as td:
            chat_db = Path(td) / "chat.db"
            chat_db.write_bytes(b"fixture")
            with mock.patch.object(helper, "CHAT_DB_PATH", chat_db):
                result = helper.action_status({}, None, {}, [])

        self.assertEqual(result["product_id"], "claudecowork-imessage")
        self.assertEqual(result["host_display_name"], "Claude Cowork")
        self.assertEqual(
            result["launchd_label"], "com.jeffhuber.claudecowork-imessage"
        )
        self.assertTrue(result["checks"]["chat_db_exists"])
        self.assertNotIn("text", json.dumps(result))

    def test_bad_requests_do_not_interrupt_the_queue(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-queue-") as td:
            bridge, requests, responses, log = self._runtime(Path(td))
            payloads = {
                "01-list": [],
                "02-action": {"id": "bad-action", "action": [], "params": {}},
                "03-params": {"id": "bad-params", "action": "status", "params": []},
                "04-large": {
                    "id": "large",
                    "action": "status",
                    "params": {},
                    "padding": "x" * (64 * 1024),
                },
                "06-status": {"id": "status", "action": "status", "params": {}},
            }
            for name, payload in payloads.items():
                (requests / f"request-{name}.json").write_text(json.dumps(payload))
            os.mkfifo(requests / "request-05-fifo.json", mode=0o600)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "REQUESTS_DIR", requests
            ), mock.patch.object(helper, "RESPONSES_DIR", responses), mock.patch.object(
                helper, "LOG_PATH", log
            ), mock.patch.object(helper, "load_privacy_policy", return_value=[]), mock.patch.object(
                helper, "reap_expired_nonces"
            ):
                helper.main()

            for name in ("01-list", "02-action", "03-params", "04-large", "05-fifo"):
                response = json.loads(
                    (responses / f"response-{name}.json").read_text()
                )
                self.assertFalse(response["ok"], name)
            self.assertTrue(
                json.loads((responses / "response-06-status.json").read_text())["ok"]
            )
            self.assertEqual(list(requests.iterdir()), [])

    def test_request_symlink_is_rejected_without_reading_its_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-symlink-") as td:
            bridge, requests, responses, log = self._runtime(Path(td))
            victim = bridge / "victim.json"
            victim.write_text(
                json.dumps({"id": "victim", "action": "status", "params": {}})
            )
            (requests / "request-linked.json").symlink_to(victim)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "REQUESTS_DIR", requests
            ), mock.patch.object(helper, "RESPONSES_DIR", responses), mock.patch.object(
                helper, "LOG_PATH", log
            ), mock.patch.object(helper, "load_privacy_policy", return_value=[]), mock.patch.object(
                helper, "reap_expired_nonces"
            ):
                helper.main()

            response = json.loads((responses / "response-linked.json").read_text())
            self.assertFalse(response["ok"])
            self.assertEqual(json.loads(victim.read_text())["id"], "victim")


class DoctorTests(unittest.TestCase):
    def test_missing_install_reports_actionable_json_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-doctor-") as td:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "tools" / "doctor.py"),
                    "--bridge",
                    str(Path(td) / "missing"),
                    "--json",
                    "--skip-launchd",
                    "--skip-codesign",
                    "--skip-chat-db",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"]["bridge_root"]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
