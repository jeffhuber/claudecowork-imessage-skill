from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests._helper_loader import REPO_ROOT, SKILL_ROOT, helper


class BridgeDirMixin:
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="claude-imessage-test-")
        self.addCleanup(self._tmp.cleanup)
        self._old_imessage_bridge = os.environ.get("IMESSAGE_BRIDGE_DIR")
        self._old_cowork_bridge = os.environ.get("COWORK_IMESSAGE_BRIDGE_DIR")
        tmp_path = os.path.realpath(self._tmp.name)
        os.environ["IMESSAGE_BRIDGE_DIR"] = tmp_path
        os.environ["COWORK_IMESSAGE_BRIDGE_DIR"] = tmp_path
        self.addCleanup(self._restore_bridge)

    def _restore_bridge(self) -> None:
        if self._old_imessage_bridge is None:
            os.environ.pop("IMESSAGE_BRIDGE_DIR", None)
        else:
            os.environ["IMESSAGE_BRIDGE_DIR"] = self._old_imessage_bridge
        if self._old_cowork_bridge is None:
            os.environ.pop("COWORK_IMESSAGE_BRIDGE_DIR", None)
        else:
            os.environ["COWORK_IMESSAGE_BRIDGE_DIR"] = self._old_cowork_bridge


class SendConfirmationTests(BridgeDirMixin, unittest.TestCase):
    def _nonce(self, to: str, text: str, service: str = "iMessage") -> str:
        return helper.mint_send_nonce(to, text, service)

    def test_full_payload_and_raw_recipient_reach_confirmation(self) -> None:
        to = "+14155551234"
        text = "prefix " + ("x" * 600) + " hidden suffix"
        nonce = self._nonce(to, text)
        contacts = {"4155551234": "Alice Example"}

        with mock.patch.object(
            helper, "_run_send_confirmation", return_value=True
        ) as confirm, mock.patch.object(
            helper, "_run_osascript", return_value=(0, "", "")
        ) as send:
            helper.action_send(
                {"to": to, "text": text, "send_nonce": nonce},
                None,
                contacts,
                [],
            )

        confirm.assert_called_once_with(
            to=to,
            resolved_name="Alice Example",
            service="iMessage",
            text=text,
        )
        send.assert_called_once()

    def test_cancelled_confirmation_never_calls_messages(self) -> None:
        to = "+14155551234"
        text = "do not send"
        nonce = self._nonce(to, text)

        with mock.patch.object(
            helper, "_run_send_confirmation", return_value=False
        ), mock.patch.object(helper, "_run_osascript") as send:
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                helper.action_send(
                    {"to": to, "text": text, "send_nonce": nonce},
                    None,
                    {},
                    [],
                )

        send.assert_not_called()

    def test_confirmation_helper_receives_json_on_stdin(self) -> None:
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(helper.subprocess, "run", return_value=completed) as run:
            approved = helper._run_send_confirmation(
                to="+14155551234",
                resolved_name="Alice Example",
                service="iMessage",
                text="all of this text must be visible",
            )

        self.assertTrue(approved)
        call = run.call_args
        self.assertEqual(call.args[0], [str(helper.CONFIRM_HELPER_PATH)])
        payload = json.loads(call.kwargs["input"])
        self.assertEqual(payload["client_name"], "Claude Cowork")
        self.assertEqual(payload["to"], "+14155551234")
        self.assertEqual(payload["resolved_name"], "Alice Example")
        self.assertEqual(payload["text"], "all of this text must be visible")
        self.assertNotIn("all of this text", " ".join(call.args[0]))

    def test_confirmation_helper_path_can_come_from_environment(self) -> None:
        script = """
import importlib.util
import sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("helper_env_probe", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
print(module.CONFIRM_HELPER_PATH)
"""
        expected = Path("/tmp/Bridge Pro.app/Contents/Helpers/imessage-confirm")
        env = {
            **os.environ,
            "IMESSAGE_CONFIRM_HELPER_PATH": str(expected),
            "IMESSAGE_BRIDGE_DIR": self._tmp.name,
        }
        result = subprocess.run(
            [sys.executable, "-c", script, str(SKILL_ROOT / "bin" / "helper.py")],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), str(expected))

    def test_confirmation_helper_fails_closed(self) -> None:
        for returncode, expected in ((1, False), (3, False)):
            completed = mock.Mock(returncode=returncode, stdout="", stderr="")
            with mock.patch.object(helper.subprocess, "run", return_value=completed):
                self.assertEqual(
                    helper._run_send_confirmation(
                        to="+14155551234",
                        resolved_name="",
                        service="iMessage",
                        text="hello",
                    ),
                    expected,
                )

        completed = mock.Mock(returncode=2, stdout="", stderr="bad input")
        with mock.patch.object(helper.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "confirmation helper failed"):
                helper._run_send_confirmation(
                    to="+14155551234",
                    resolved_name="",
                    service="iMessage",
                    text="hello",
                )

    def test_native_confirmation_source_defaults_to_cancel(self) -> None:
        source = (SKILL_ROOT / "bin" / "confirm_imessage_send.m").read_text()
        cancel_pos = source.index('addButtonWithTitle:@"Cancel"')
        send_pos = source.index('addButtonWithTitle:@"Send"')
        self.assertLess(cancel_pos, send_pos)
        self.assertIn('cancelButton.keyEquivalent = @"\\r"', source)
        self.assertIn('sendButton.keyEquivalent = @""', source)
        self.assertIn("timerWithTimeInterval:kConfirmationTimeoutSeconds", source)
        self.assertIn("forMode:NSModalPanelRunLoopMode", source)
        self.assertIn('@"client_name"', source)
        self.assertNotIn("scheduledTimerWithTimeInterval", source)


class SensitiveArtifactTests(unittest.TestCase):
    def test_attributed_body_failure_log_contains_no_blob_bytes(self) -> None:
        blob = b"streamtyped-secret-message-material"
        with mock.patch.object(helper, "log") as log:
            self.assertEqual(helper._attributed_fail(blob, "test failure"), "")

        message = log.call_args.args[0]
        self.assertIn("bytes=", message)
        self.assertNotIn(blob.hex(), message)
        self.assertNotIn("secret", message)

    def test_responses_are_mode_600_and_atomically_written(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-response-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            control = bridge / "control"
            control.mkdir(mode=0o700)
            response_dir = control / "responses"
            response_dir.mkdir(mode=0o700)
            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "RESPONSES_DIR", response_dir
            ):
                helper.write_response("abc123", {"ok": True, "text": "private"})

            response = response_dir / "response-abc123.json"
            self.assertTrue(response.exists())
            self.assertEqual(stat.S_IMODE(response_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(response.stat().st_mode), 0o600)
            self.assertEqual(list(response_dir.glob("*.tmp")), [])

    def test_main_accepts_private_control_and_queue_directories(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-control-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            control_dir = bridge / "control"
            requests_dir = control_dir / "requests"
            responses_dir = control_dir / "responses"
            for path in (requests_dir, responses_dir):
                path.mkdir(parents=True, mode=0o700)
            control_dir.chmod(0o700)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "LOG_PATH", control_dir / "log.txt"
            ), mock.patch.object(
                helper, "REQUESTS_DIR", requests_dir
            ), mock.patch.object(helper, "RESPONSES_DIR", responses_dir), mock.patch.object(
                helper, "load_blocklist", return_value=[]
            ), mock.patch.object(helper, "reap_expired_nonces"):
                helper.main()

            for path in (control_dir, requests_dir, responses_dir):
                with self.subTest(path=path):
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_response_reaper_keeps_fresh_and_removes_stale(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-response-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            control = bridge / "control"
            control.mkdir(mode=0o700)
            response_dir = control / "responses"
            response_dir.mkdir(mode=0o700)
            fresh = response_dir / "response-fresh.json"
            stale = response_dir / "response-stale.json"
            legacy = response_dir / "response-legacy.json"
            fresh.write_text("{}")
            stale.write_text("{}")
            legacy.write_text("{}")
            fresh.chmod(0o600)
            stale.chmod(0o600)
            legacy.chmod(0o644)
            old = time.time() - helper.RESPONSE_TTL_S - 10
            os.utime(stale, (old, old))
            os.utime(legacy, (old, old))

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "RESPONSES_DIR", response_dir
            ):
                helper.reap_expired_responses()

            self.assertTrue(fresh.exists())
            self.assertFalse(stale.exists())
            self.assertFalse(legacy.exists())

    def test_response_reaper_tolerates_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-response-missing-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            control = bridge / "control"
            control.mkdir(mode=0o700)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "RESPONSES_DIR", control / "responses"
            ):
                helper.reap_expired_responses()

    def test_log_is_mode_600_and_rotated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-log-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            control = bridge / "control"
            control.mkdir(mode=0o700)
            log_path = control / "log.txt"
            log_path.write_text("x" * 32)
            log_path.chmod(0o600)
            first_archive = control / "log.txt.1"
            first_archive.write_text("older")
            first_archive.chmod(0o600)
            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "LOG_PATH", log_path
            ), mock.patch.object(
                helper, "LOG_MAX_BYTES", 16
            ):
                helper.log("fresh diagnostic")

            self.assertEqual(stat.S_IMODE(control.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(log_path.stat().st_mode), 0o600)
            self.assertIn("fresh diagnostic", log_path.read_text())
            self.assertEqual(first_archive.read_text(), "x" * 32)
            self.assertEqual(stat.S_IMODE(first_archive.stat().st_mode), 0o600)
            second_archive = control / "log.txt.2"
            self.assertEqual(second_archive.read_text(), "older")
            self.assertEqual(stat.S_IMODE(second_archive.stat().st_mode), 0o600)

    def test_personal_blocklist_is_gitignored(self) -> None:
        gitignore = (REPO_ROOT / ".gitignore").read_text().splitlines()
        self.assertIn(
            "skills/imessage-review/contacts/blocked_chats.txt", gitignore
        )

    def test_log_rejects_symlinks_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-log-symlink-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            control = bridge / "control"
            control.mkdir(mode=0o700)
            victim = bridge / "victim.txt"
            victim.write_text("unchanged\n")
            victim.chmod(0o600)
            (control / "log.txt").symlink_to(victim)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "LOG_PATH", control / "log.txt"
            ):
                helper.log("must not follow")

            self.assertEqual(victim.read_text(), "unchanged\n")

    def test_log_rejects_symlinked_runtime_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-dir-symlink-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            victim = bridge / "victim-dir"
            victim.mkdir(mode=0o755)
            (bridge / "control").symlink_to(victim, target_is_directory=True)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "LOG_PATH", bridge / "control" / "log.txt"
            ):
                helper.log("must not follow")

            self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o755)
            self.assertFalse((victim / "log.txt").exists())

    def test_runtime_directory_permissions_are_not_repaired(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-dir-mode-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            control = bridge / "control"
            control.mkdir(mode=0o755)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "LOG_PATH", control / "log.txt"
            ), mock.patch.object(helper, "REQUESTS_DIR", control / "requests"), mock.patch.object(
                helper, "RESPONSES_DIR", control / "responses"
            ), self.assertRaises(helper.UnsafeRuntimePath):
                helper.main()

            self.assertEqual(stat.S_IMODE(control.stat().st_mode), 0o755)

    def test_bridge_root_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-root-symlink-test-") as td:
            parent = Path(os.path.realpath(td))
            victim = parent / "victim"
            victim.mkdir(mode=0o700)
            bridge = parent / "bridge"
            bridge.symlink_to(victim, target_is_directory=True)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), self.assertRaises(
                helper.UnsafeRuntimePath
            ):
                with helper._private_directory_fd(bridge / "control", create=True):
                    pass

            self.assertEqual(list(victim.iterdir()), [])

    def test_response_writer_rejects_symlinked_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="grokbot-response-symlink-test-") as td:
            bridge = Path(os.path.realpath(td))
            bridge.chmod(0o700)
            control = bridge / "control"
            control.mkdir(mode=0o700)
            victim = bridge / "victim-dir"
            victim.mkdir(mode=0o755)
            responses = control / "responses"
            responses.symlink_to(victim, target_is_directory=True)

            with mock.patch.object(helper, "BRIDGE_ROOT", bridge), mock.patch.object(
                helper, "RESPONSES_DIR", responses
            ), self.assertRaises(RuntimeError):
                helper.write_response("symlink", {"ok": True})

            self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o755)
            self.assertEqual(list(victim.iterdir()), [])

    def test_launchd_does_not_open_user_controlled_log_path(self) -> None:
        plist = (
            SKILL_ROOT
            / "com.jeffhuber.claudecowork-imessage.plist.template"
        ).read_text()
        self.assertNotIn("{{BRIDGE_ROOT}}/control/log.txt", plist)
        self.assertEqual(plist.count("<string>/dev/null</string>"), 2)


class ProductModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="product-mode-test-")
        self.addCleanup(self._tmp.cleanup)
        self._saved_env = {}
        for var in ("IMESSAGE_PRODUCT_ID", "IMESSAGE_POLICY_DIR", "IMESSAGE_SEND_GATE_PATH",
                    "IMESSAGE_CONFIRM_HELPER_PATH", "COWORK_IMESSAGE_READ_POLICY"):
            self._saved_env[var] = os.environ.get(var)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        for var, value in self._saved_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    def test_missing_read_policy_defaults_to_allowlist_in_product_mode(self) -> None:
        """Verify that product mode defaults to allowlist when read_policy.txt is missing."""
        policy_dir = Path(self._tmp.name)
        policy_dir.mkdir(parents=True, exist_ok=True)
        
        # Temporarily set wrapper mode to product by patching
        old_wrapper_mode = helper.WRAPPER_MODE
        old_policy_root = helper.POLICY_ROOT
        old_read_policy_path = helper.READ_POLICY_PATH
        
        try:
            helper.WRAPPER_MODE = "product"
            helper.POLICY_ROOT = policy_dir
            helper.READ_POLICY_PATH = policy_dir / "read_policy.txt"
            
            policy = helper.load_privacy_policy()
            self.assertEqual(policy.mode, "allowlist")
        finally:
            helper.WRAPPER_MODE = old_wrapper_mode
            helper.POLICY_ROOT = old_policy_root
            helper.READ_POLICY_PATH = old_read_policy_path

    def test_missing_read_policy_defaults_to_blocklist_in_baked_mode(self) -> None:
        """Verify that baked mode defaults to blocklist when read_policy.txt is missing."""
        policy_dir = Path(self._tmp.name)
        policy_dir.mkdir(parents=True, exist_ok=True)
        
        old_wrapper_mode = helper.WRAPPER_MODE
        old_policy_root = helper.POLICY_ROOT
        old_read_policy_path = helper.READ_POLICY_PATH
        
        try:
            helper.WRAPPER_MODE = "baked"
            helper.POLICY_ROOT = policy_dir
            helper.READ_POLICY_PATH = policy_dir / "read_policy.txt"
            
            policy = helper.load_privacy_policy()
            self.assertEqual(policy.mode, "blocklist")
        finally:
            helper.WRAPPER_MODE = old_wrapper_mode
            helper.POLICY_ROOT = old_policy_root
            helper.READ_POLICY_PATH = old_read_policy_path

    def test_policy_file_permission_rejection_in_product_mode(self) -> None:
        """Verify that policy files with bad permissions are rejected in product mode."""
        policy_dir = Path(self._tmp.name)
        policy_dir.mkdir(parents=True, exist_ok=True)
        
        # Create policy file with group-writable permissions
        blocked_file = policy_dir / "blocked_chats.txt"
        blocked_file.write_text("+14155551234\n")
        blocked_file.chmod(0o664)  # group-writable
        
        old_wrapper_mode = helper.WRAPPER_MODE
        old_blocklist_path = helper.BLOCKLIST_PATH
        
        try:
            helper.WRAPPER_MODE = "product"
            helper.BLOCKLIST_PATH = blocked_file
            
            with mock.patch.object(helper, "log") as mock_log:
                policy = helper.load_privacy_policy()
                # Policy file should be rejected due to permissions
                self.assertEqual(len(policy.blocklist), 0)
                
                # Check that log was called with permission rejection message
                logged = " ".join(str(call.args[0]) for call in mock_log.call_args_list)
                self.assertIn("group/world-writable", logged)
        finally:
            helper.WRAPPER_MODE = old_wrapper_mode
            helper.BLOCKLIST_PATH = old_blocklist_path

    def test_group_writable_read_policy_treated_as_missing_in_product_mode(self) -> None:
        """Verify that group-writable read_policy.txt containing 'blocklist' does NOT become blocklist in product mode."""
        policy_dir = Path(self._tmp.name)
        policy_dir.mkdir(parents=True, exist_ok=True)
        
        # Create read_policy.txt with group-writable permissions
        read_policy = policy_dir / "read_policy.txt"
        read_policy.write_text("blocklist\n")
        read_policy.chmod(0o664)  # group-writable
        
        old_wrapper_mode = helper.WRAPPER_MODE
        old_policy_root = helper.POLICY_ROOT
        old_read_policy_path = helper.READ_POLICY_PATH
        
        try:
            helper.WRAPPER_MODE = "product"
            helper.POLICY_ROOT = policy_dir
            helper.READ_POLICY_PATH = read_policy
            
            with mock.patch.object(helper, "log") as mock_log:
                policy = helper.load_privacy_policy()
                # Should default to allowlist (fail closed), not blocklist
                self.assertEqual(policy.mode, "allowlist")
                
                # Check that log was called with permission rejection message
                logged = " ".join(str(call.args[0]) for call in mock_log.call_args_list)
                self.assertIn("group/world-writable", logged)
        finally:
            helper.WRAPPER_MODE = old_wrapper_mode
            helper.POLICY_ROOT = old_policy_root
            helper.READ_POLICY_PATH = old_read_policy_path

    def test_policy_file_accepts_correct_permissions_in_product_mode(self) -> None:
        """Verify that policy files with correct permissions are loaded in product mode."""
        policy_dir = Path(self._tmp.name)
        policy_dir.mkdir(parents=True, exist_ok=True)
        
        # Create policy file with correct permissions
        allowed_file = policy_dir / "allowed_chats.txt"
        allowed_file.write_text("+14155551234\n")
        allowed_file.chmod(0o600)
        
        old_wrapper_mode = helper.WRAPPER_MODE
        old_allowlist_path = helper.ALLOWLIST_PATH
        
        try:
            helper.WRAPPER_MODE = "product"
            helper.ALLOWLIST_PATH = allowed_file
            
            policy = helper.load_privacy_policy()
            self.assertEqual(len(policy.allowlist), 1)
        finally:
            helper.WRAPPER_MODE = old_wrapper_mode
            helper.ALLOWLIST_PATH = old_allowlist_path

    def test_action_status_includes_product_fields(self) -> None:
        """Verify that action_status returns the new product fields."""
        status = helper.action_status({}, None, {}, helper.load_privacy_policy())
        
        # Verify all required fields are present
        self.assertIn("product_id", status)
        self.assertIn("wrapper_mode", status)
        self.assertIn("policy_dir", status)
        
        # Verify types
        self.assertIsInstance(status["product_id"], str)
        self.assertIsInstance(status["wrapper_mode"], str)
        self.assertIsInstance(status["policy_dir"], str)
        
        # Verify wrapper_mode is valid
        self.assertIn(status["wrapper_mode"], ("product", "baked"))


if __name__ == "__main__":
    unittest.main()
