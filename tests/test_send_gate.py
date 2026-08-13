"""Tests for send_gate.py — helper-side preview/confirm gate (v0.4.0+)."""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

# Match _helper_loader.py: put skills/imessage-review/bin on sys.path so
# `import send_gate` resolves without depending on helper.py.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BIN = _REPO_ROOT / "skills" / "imessage-review" / "bin"
if str(_BIN) not in sys.path:
    sys.path.insert(0, str(_BIN))

import send_gate  # noqa: E402
from send_gate import (  # noqa: E402
    SEND_NONCE_TTL,
    SendGateError,
    consume_send_nonce,
    mint_send_nonce,
    reap_expired_nonces,
)


class TestSendGate(unittest.TestCase):
    def setUp(self):
        # Fresh bridge dir per test; env override routes all paths there.
        self._tmp = str(pathlib.Path(
            tempfile.mkdtemp(prefix="claudecowork-imessage-test-")
        ).resolve())
        self._old_imessage_bridge = os.environ.get("IMESSAGE_BRIDGE_DIR")
        self._old_cowork_bridge = os.environ.get("COWORK_IMESSAGE_BRIDGE_DIR")
        os.environ["IMESSAGE_BRIDGE_DIR"] = self._tmp
        os.environ["COWORK_IMESSAGE_BRIDGE_DIR"] = self._tmp

    def tearDown(self):
        if self._old_imessage_bridge is None:
            os.environ.pop("IMESSAGE_BRIDGE_DIR", None)
        else:
            os.environ["IMESSAGE_BRIDGE_DIR"] = self._old_imessage_bridge
        if self._old_cowork_bridge is None:
            os.environ.pop("COWORK_IMESSAGE_BRIDGE_DIR", None)
        else:
            os.environ["COWORK_IMESSAGE_BRIDGE_DIR"] = self._old_cowork_bridge
        shutil.rmtree(self._tmp, ignore_errors=True)

    # --- happy path ----------------------------------------------------

    def test_nonce_round_trip(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        # Should not raise.
        consume_send_nonce(n, "+15551234", "hi", "iMessage")

    def test_nonce_is_deleted_on_success(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        consume_send_nonce(n, "+15551234", "hi", "iMessage")
        path = pathlib.Path(self._tmp, "nonces", f"{n}.json")
        self.assertFalse(path.exists())

    def test_each_mint_returns_fresh_nonce(self):
        a = mint_send_nonce("+15551234", "hi", "iMessage")
        b = mint_send_nonce("+15551234", "hi", "iMessage")
        self.assertNotEqual(a, b)

    # --- replay / missing / malformed ----------------------------------

    def test_replay_after_consume_rejected(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        consume_send_nonce(n, "+15551234", "hi", "iMessage")
        with self.assertRaisesRegex(SendGateError, "not recognized"):
            consume_send_nonce(n, "+15551234", "hi", "iMessage")

    def test_missing_nonce_rejected_none(self):
        with self.assertRaisesRegex(SendGateError, "missing nonce"):
            consume_send_nonce(None, "+15551234", "hi", "iMessage")

    def test_missing_nonce_rejected_empty(self):
        with self.assertRaisesRegex(SendGateError, "missing nonce"):
            consume_send_nonce("", "+15551234", "hi", "iMessage")

    def test_invalid_nonce_format_rejected(self):
        with self.assertRaisesRegex(SendGateError, "invalid nonce format"):
            consume_send_nonce("../../etc/passwd", "+15551234", "hi", "iMessage")

    def test_unknown_nonce_rejected(self):
        # Well-formed but not minted.
        with self.assertRaisesRegex(SendGateError, "not recognized"):
            consume_send_nonce("abcDEF_-123", "+15551234", "hi", "iMessage")

    # --- payload binding -----------------------------------------------

    def test_payload_mismatch_to(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        with self.assertRaisesRegex(SendGateError, "differs from preview"):
            consume_send_nonce(n, "+15559999", "hi", "iMessage")

    def test_payload_mismatch_body(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        with self.assertRaisesRegex(SendGateError, "differs from preview"):
            consume_send_nonce(n, "+15551234", "hello", "iMessage")

    def test_payload_mismatch_service(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        with self.assertRaisesRegex(SendGateError, "differs from preview"):
            consume_send_nonce(n, "+15551234", "hi", "SMS")

    def test_mismatch_deletes_nonce(self):
        # A tampered send should burn the nonce so it can't be retried with
        # the correct body.
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        with self.assertRaises(SendGateError):
            consume_send_nonce(n, "+15551234", "hello", "iMessage")
        with self.assertRaisesRegex(SendGateError, "not recognized"):
            consume_send_nonce(n, "+15551234", "hi", "iMessage")

    # --- expiry --------------------------------------------------------

    def test_expired_nonce_rejected(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        future = time.time() + SEND_NONCE_TTL + 1
        with patch("send_gate.time.time", return_value=future):
            with self.assertRaisesRegex(SendGateError, "expired"):
                consume_send_nonce(n, "+15551234", "hi", "iMessage")

    def test_expired_nonce_deleted(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        path = pathlib.Path(self._tmp, "nonces", f"{n}.json")
        future = time.time() + SEND_NONCE_TTL + 1
        with patch("send_gate.time.time", return_value=future):
            with self.assertRaises(SendGateError):
                consume_send_nonce(n, "+15551234", "hi", "iMessage")
        self.assertFalse(path.exists())

    def test_reaper_cleans_expired(self):
        mint_send_nonce("+15551234", "hi", "iMessage")
        mint_send_nonce("+15559999", "hello", "iMessage")
        future = time.time() + SEND_NONCE_TTL + 1
        with patch("send_gate.time.time", return_value=future):
            reap_expired_nonces()
        remaining = list(pathlib.Path(self._tmp, "nonces").glob("*.json"))
        self.assertEqual(remaining, [])

    def test_reaper_leaves_fresh_nonces_alone(self):
        n = mint_send_nonce("+15551234", "hi", "iMessage")
        reap_expired_nonces()
        # Still usable.
        consume_send_nonce(n, "+15551234", "hi", "iMessage")

    # --- environment requirement ---------------------------------------

    def test_bridge_dir_requires_env_var(self):
        os.environ.pop("COWORK_IMESSAGE_BRIDGE_DIR", None)
        os.environ.pop("IMESSAGE_BRIDGE_DIR", None)
        with self.assertRaisesRegex(RuntimeError, "IMESSAGE_BRIDGE_DIR is required"):
            send_gate._bridge_dir()

    def test_bridge_dir_prefers_new_env_var_name(self):
        """New name IMESSAGE_BRIDGE_DIR takes precedence."""
        new_path = tempfile.mkdtemp(prefix="new-bridge-")
        old_path = tempfile.mkdtemp(prefix="old-bridge-")
        try:
            os.environ["IMESSAGE_BRIDGE_DIR"] = new_path
            os.environ["COWORK_IMESSAGE_BRIDGE_DIR"] = old_path
            self.assertEqual(str(send_gate._bridge_dir()), os.path.abspath(new_path))
        finally:
            os.environ.pop("IMESSAGE_BRIDGE_DIR", None)
            os.environ.pop("COWORK_IMESSAGE_BRIDGE_DIR", None)
            for p in (new_path, old_path):
                try:
                    os.rmdir(p)
                except Exception:
                    pass

    def test_bridge_dir_accepts_old_env_var_name(self):
        """Old name COWORK_IMESSAGE_BRIDGE_DIR still works as fallback."""
        old_path = tempfile.mkdtemp(prefix="old-bridge-fallback-")
        try:
            os.environ.pop("IMESSAGE_BRIDGE_DIR", None)
            os.environ["COWORK_IMESSAGE_BRIDGE_DIR"] = old_path
            self.assertEqual(str(send_gate._bridge_dir()), os.path.abspath(old_path))
        finally:
            os.environ.pop("COWORK_IMESSAGE_BRIDGE_DIR", None)
            try:
                os.rmdir(old_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
