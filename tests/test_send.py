"""Tests for the send-side actions — send_preview, send, and their validators.

The send path shells out to /usr/bin/osascript. These tests never invoke
osascript for real; we monkey-patch `helper._run_osascript` so the tests
run on any OS and don't require Messages.app or Automation permission.

Coverage:
  - validate_send_text — length, empty, control-char rejection, emoji.
  - validate_service — whitelist enforcement, default.
  - _escape_as_string — AppleScript string-literal escaping.
  - action_send_preview — is non-destructive, resolves contact names,
    surfaces the blocked flag.
  - action_send — builds the right AppleScript, refuses to send to
    blocked targets, cleans up the tempfile even on failure, maps a
    nonzero osascript exit into a RuntimeError.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _helper_loader import helper  # noqa: E402

# helper.py loads send_gate via importlib (because the C wrapper uses -I,
# which takes sys.path[0] out from under a plain `import`). That loader
# creates a DISTINCT module object — so `helper._send_gate.SendGateError`
# is a different class from `import send_gate`'s SendGateError. Tests must
# reach for helper's copy if they want `isinstance` to work against what
# the helper actually raises.
send_gate = helper._send_gate


def _mint(to, text, service="iMessage"):
    """Produce a fresh payload-bound send_nonce so tests can call
    action_send without first going through send_preview."""
    return send_gate.mint_send_nonce(to, text, service)


class _BridgeDirMixin:
    """Route send_gate state (mint_send_nonce, consume_send_nonce, reap)
    at a per-test tempdir so tests don't touch ~/cowork-imessage/nonces."""

    def setUp(self):
        self._bridge_tmp = tempfile.mkdtemp(prefix="cowork-imessage-test-")
        os.environ["COWORK_IMESSAGE_BRIDGE_DIR"] = self._bridge_tmp

    def tearDown(self):
        os.environ.pop("COWORK_IMESSAGE_BRIDGE_DIR", None)
        shutil.rmtree(self._bridge_tmp, ignore_errors=True)


class ValidateSendTextTests(unittest.TestCase):

    def test_valid_short(self):
        self.assertEqual(helper.validate_send_text("hello"), "hello")

    def test_valid_with_newlines(self):
        s = "line 1\nline 2\nline 3"
        self.assertEqual(helper.validate_send_text(s), s)

    def test_emoji_allowed(self):
        s = "running 5 min late 🏃‍♂️💨"
        self.assertEqual(helper.validate_send_text(s), s)

    def test_at_max_length(self):
        s = "x" * helper.MAX_SEND_LEN
        self.assertEqual(helper.validate_send_text(s), s)

    def test_over_max_length(self):
        with self.assertRaises(ValueError):
            helper.validate_send_text("x" * (helper.MAX_SEND_LEN + 1))

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_send_text("")

    def test_non_string_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_send_text(123)
        with self.assertRaises(ValueError):
            helper.validate_send_text(None)

    def test_null_byte_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_send_text("hello\x00world")

    def test_bell_char_rejected(self):
        # \x07 (BEL) — no legitimate reason for this in a text message.
        with self.assertRaises(ValueError):
            helper.validate_send_text("hey\x07 there")

    def test_escape_char_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_send_text("esc\x1b[31m")


class ValidateServiceTests(unittest.TestCase):

    def test_imessage(self):
        self.assertEqual(helper.validate_service("iMessage"), "iMessage")

    def test_sms(self):
        self.assertEqual(helper.validate_service("SMS"), "SMS")

    def test_default_none(self):
        self.assertEqual(helper.validate_service(None), "iMessage")

    def test_rejects_lowercase(self):
        # Enforce the enum literal exactly — AppleScript is case-sensitive
        # for its service-type values.
        with self.assertRaises(ValueError):
            helper.validate_service("imessage")

    def test_rejects_unknown(self):
        with self.assertRaises(ValueError):
            helper.validate_service("WhatsApp")


class EscapeAsStringTests(unittest.TestCase):
    """AppleScript string-literal escaping. Only `"` and `\\` need escaping."""

    def test_plain(self):
        self.assertEqual(helper._escape_as_string("hello"), "hello")

    def test_escapes_double_quote(self):
        self.assertEqual(helper._escape_as_string('she said "hi"'),
                         'she said \\"hi\\"')

    def test_escapes_backslash(self):
        # One Python-level backslash → two AppleScript-level.
        self.assertEqual(helper._escape_as_string("C:\\foo"),
                         "C:\\\\foo")

    def test_backslash_ordering(self):
        # Backslash must be escaped BEFORE double-quote, otherwise the
        # escape sequence for " gets double-escaped. Smoke test.
        self.assertEqual(helper._escape_as_string('a\\"b'),
                         'a\\\\\\"b')

    def test_unicode_untouched(self):
        # AppleScript string literals accept Unicode; we don't try to encode.
        self.assertEqual(helper._escape_as_string("café 🎉"), "café 🎉")


class SendPreviewTests(_BridgeDirMixin, unittest.TestCase):
    """`send_preview` returns the resolved preview dict plus a single-use
    send_nonce. Aside from the nonce file it writes under
    `<bridge>/nonces/` it has no side effects."""

    def setUp(self):
        super().setUp()
        self.contacts = {"4155551234": "Alice Example"}
        self.blocklist = ["+18005551212"]

    def test_basic_phone_preview(self):
        out = helper.action_send_preview(
            {"to": "+14155551234", "text": "hey"},
            None, self.contacts, self.blocklist,
        )
        self.assertEqual(out["preview"]["to"], "+14155551234")
        self.assertEqual(out["preview"]["resolved_name"], "Alice Example")
        self.assertEqual(out["preview"]["service"], "iMessage")
        self.assertEqual(out["preview"]["text"], "hey")
        self.assertEqual(out["preview"]["text_length"], 3)
        self.assertFalse(out["preview"]["blocked"])
        # v0.4.0+: a nonce is minted and surfaced for the subsequent send.
        self.assertIn("send_nonce", out)
        self.assertIsInstance(out["send_nonce"], str)
        self.assertTrue(out["send_nonce"])
        self.assertEqual(out["send_nonce_ttl_seconds"], send_gate.SEND_NONCE_TTL)

    def test_default_service_is_imessage(self):
        out = helper.action_send_preview(
            {"to": "+14155551234", "text": "hey"},
            None, self.contacts, self.blocklist,
        )
        self.assertEqual(out["preview"]["service"], "iMessage")

    def test_explicit_sms_preview(self):
        out = helper.action_send_preview(
            {"to": "+14155551234", "text": "hey", "service": "SMS"},
            None, self.contacts, self.blocklist,
        )
        self.assertEqual(out["preview"]["service"], "SMS")

    def test_blocked_flag_surfaced(self):
        out = helper.action_send_preview(
            {"to": "+18005551212", "text": "hello"},
            None, self.contacts, self.blocklist,
        )
        self.assertTrue(out["preview"]["blocked"])

    def test_email_has_no_resolved_name(self):
        # Contacts loader keys on 10-digit phones, so email handles don't
        # resolve — that's expected.
        out = helper.action_send_preview(
            {"to": "alice@example.com", "text": "hi"},
            None, self.contacts, self.blocklist,
        )
        self.assertEqual(out["preview"]["resolved_name"], "")

    def test_invalid_text_propagates(self):
        with self.assertRaises(ValueError):
            helper.action_send_preview(
                {"to": "+14155551234", "text": ""},
                None, self.contacts, self.blocklist,
            )

    def test_invalid_service_propagates(self):
        with self.assertRaises(ValueError):
            helper.action_send_preview(
                {"to": "+14155551234", "text": "hi", "service": "WhatsApp"},
                None, self.contacts, self.blocklist,
            )


class SendActionTests(_BridgeDirMixin, unittest.TestCase):
    """End-to-end send behavior with osascript fully mocked out."""

    def setUp(self):
        super().setUp()
        self.contacts = {"4155551234": "Alice Example"}
        self.blocklist = ["+18005551212"]

    def _run(self, params, osascript_result=(0, "", ""), skip_nonce=False):
        """Invoke action_send with a mocked osascript. Returns (result, script).

        By default mints a fresh send_nonce for the params' (to, text, service)
        before calling action_send, so callers don't have to open-code the
        preview step. Pass skip_nonce=True to test the gate's refusal path.
        """
        captured = {}

        def fake_run(script, timeout=None):
            captured["script"] = script
            captured["timeout"] = timeout
            return osascript_result

        if not skip_nonce and "send_nonce" not in params:
            params = dict(params)  # don't mutate caller's dict
            params["send_nonce"] = _mint(
                params["to"],
                params["text"],
                params.get("service", "iMessage"),
            )

        with mock.patch.object(helper, "_run_osascript", side_effect=fake_run):
            result = helper.action_send(
                params, None, self.contacts, self.blocklist,
            )
        return result, captured

    def test_successful_send(self):
        result, _ = self._run(
            {"to": "+14155551234", "text": "running 5 late"},
        )
        self.assertIn("sent", result)
        self.assertEqual(result["sent"]["to"], "+14155551234")
        self.assertEqual(result["sent"]["resolved_name"], "Alice Example")
        self.assertEqual(result["sent"]["service"], "iMessage")
        self.assertEqual(result["sent"]["text_length"], len("running 5 late"))
        self.assertIn("sent_at", result["sent"])

    def test_script_shape_imessage(self):
        _, captured = self._run(
            {"to": "+14155551234", "text": "hi"},
        )
        script = captured["script"]
        self.assertIn('tell application "Messages"', script)
        self.assertIn("service type = iMessage", script)
        self.assertIn('buddy "+14155551234"', script)
        self.assertIn("read POSIX file", script)
        # The body itself must NOT be in the script — it goes via tempfile.
        self.assertNotIn("hi\n", script)

    def test_script_shape_sms(self):
        _, captured = self._run(
            {"to": "+14155551234", "text": "hi", "service": "SMS"},
        )
        self.assertIn("service type = SMS", captured["script"])
        self.assertNotIn("service type = iMessage", captured["script"])

    def test_recipient_escaping(self):
        # If someone passes a recipient that contains a double-quote, the
        # escape should neutralize it. validate_chat allows the char through
        # because it's not clearly invalid for emails/group IDs.
        _, captured = self._run(
            {"to": 'foo"bar@example.com', "text": "x"},
        )
        # The AppleScript literal should have the quote escaped.
        self.assertIn('foo\\"bar@example.com', captured["script"])

    def test_body_goes_to_tempfile(self):
        # Verify the POSIX-file path referenced in the script actually
        # existed during the call — by capturing it and checking that
        # after the call the file has been cleaned up.
        captured = {}

        def fake_run(script, timeout=None):
            captured["script"] = script
            # Parse out the POSIX file path.
            import re
            m = re.search(r'read POSIX file "([^"]+)"', script)
            self.assertIsNotNone(m)
            captured["path"] = m.group(1).replace("\\\\", "\\")
            # While osascript is "running" the file should still exist.
            self.assertTrue(os.path.exists(captured["path"]))
            with open(captured["path"], encoding="utf-8") as f:
                captured["body_content"] = f.read()
            return (0, "", "")

        with mock.patch.object(helper, "_run_osascript", side_effect=fake_run):
            helper.action_send(
                {"to": "+14155551234", "text": "body via tempfile 🎉",
                 "send_nonce": _mint("+14155551234", "body via tempfile 🎉")},
                None, self.contacts, self.blocklist,
            )

        self.assertEqual(captured["body_content"], "body via tempfile 🎉")
        # After the call, the tempfile must be gone.
        self.assertFalse(os.path.exists(captured["path"]))

    def test_tempfile_cleaned_up_on_failure(self):
        # Simulate osascript exiting nonzero — the finally: block must
        # still delete the tempfile.
        captured = {}

        def fake_run(script, timeout=None):
            import re
            m = re.search(r'read POSIX file "([^"]+)"', script)
            captured["path"] = m.group(1).replace("\\\\", "\\")
            return (1, "", "Messages got an error: not authorized")

        with mock.patch.object(helper, "_run_osascript", side_effect=fake_run):
            with self.assertRaises(RuntimeError) as ctx:
                helper.action_send(
                    {"to": "+14155551234", "text": "x",
                     "send_nonce": _mint("+14155551234", "x")},
                    None, self.contacts, self.blocklist,
                )

        self.assertIn("not authorized", str(ctx.exception))
        self.assertFalse(os.path.exists(captured["path"]),
                         "tempfile leaked after osascript failure")

    def test_blocked_target_refused(self):
        # No osascript call should happen at all.
        with mock.patch.object(helper, "_run_osascript") as mocked:
            with self.assertRaises(ValueError) as ctx:
                helper.action_send(
                    {"to": "+18005551212", "text": "hey"},
                    None, self.contacts, self.blocklist,
                )
        self.assertIn("blocked_chats.txt", str(ctx.exception))
        mocked.assert_not_called()

    def test_empty_text_refused_before_osascript(self):
        with mock.patch.object(helper, "_run_osascript") as mocked:
            with self.assertRaises(ValueError):
                helper.action_send(
                    {"to": "+14155551234", "text": ""},
                    None, self.contacts, self.blocklist,
                )
        mocked.assert_not_called()

    def test_unknown_service_refused_before_osascript(self):
        with mock.patch.object(helper, "_run_osascript") as mocked:
            with self.assertRaises(ValueError):
                helper.action_send(
                    {"to": "+14155551234", "text": "x", "service": "Signal"},
                    None, self.contacts, self.blocklist,
                )
        mocked.assert_not_called()


class SendActionsDeclareNoDBTests(unittest.TestCase):
    """The send actions should NOT pay the chat.db copy cost — they don't
    read messages, only send. The dispatch loop keys on `needs_db`."""

    def test_send_declares_no_db(self):
        self.assertFalse(getattr(helper.action_send, "needs_db", True))

    def test_send_preview_declares_no_db(self):
        self.assertFalse(getattr(helper.action_send_preview, "needs_db", True))

    def test_review_still_needs_db(self):
        # Regression: don't accidentally mark read actions as no-db.
        self.assertTrue(getattr(helper.action_review, "needs_db", True))


class SendGateIntegrationTests(_BridgeDirMixin, unittest.TestCase):
    """action_send must refuse anything that fails the preview/confirm
    gate — missing nonce, stale nonce, or a body that doesn't match what
    was previewed. osascript is mocked so we can assert it is NEVER
    called on these failure paths."""

    def setUp(self):
        super().setUp()
        self.contacts = {"4155551234": "Alice Example"}
        self.blocklist = ["+18005551212"]

    def _try_send(self, params):
        with mock.patch.object(helper, "_run_osascript") as mocked:
            try:
                helper.action_send(params, None, self.contacts, self.blocklist)
                raised = None
            except Exception as e:
                raised = e
        return raised, mocked

    def test_send_without_nonce_refused(self):
        raised, mocked = self._try_send(
            {"to": "+14155551234", "text": "hi"},
        )
        self.assertIsInstance(raised, send_gate.SendGateError)
        self.assertIn("missing nonce", str(raised))
        mocked.assert_not_called()

    def test_send_with_bogus_nonce_refused(self):
        raised, mocked = self._try_send(
            {"to": "+14155551234", "text": "hi",
             "send_nonce": "abcDEF_-123"},  # well-formed but never minted
        )
        self.assertIsInstance(raised, send_gate.SendGateError)
        self.assertIn("not recognized", str(raised))
        mocked.assert_not_called()

    def test_payload_swap_between_preview_and_send_refused(self):
        # Mint a nonce for "hi", then try to send "BAD" with it.
        nonce = _mint("+14155551234", "hi")
        raised, mocked = self._try_send(
            {"to": "+14155551234", "text": "BAD",
             "send_nonce": nonce},
        )
        self.assertIsInstance(raised, send_gate.SendGateError)
        self.assertIn("differs from preview", str(raised))
        mocked.assert_not_called()

    def test_nonce_is_single_use(self):
        # First send consumes the nonce; second send with same nonce fails.
        nonce = _mint("+14155551234", "hi")
        with mock.patch.object(helper, "_run_osascript", return_value=(0, "", "")):
            helper.action_send(
                {"to": "+14155551234", "text": "hi", "send_nonce": nonce},
                None, self.contacts, self.blocklist,
            )
        raised, mocked = self._try_send(
            {"to": "+14155551234", "text": "hi", "send_nonce": nonce},
        )
        self.assertIsInstance(raised, send_gate.SendGateError)
        self.assertIn("not recognized", str(raised))
        mocked.assert_not_called()

    def test_preview_and_send_round_trip(self):
        # End-to-end: preview returns a nonce, send with that nonce works.
        preview = helper.action_send_preview(
            {"to": "+14155551234", "text": "hello"},
            None, self.contacts, self.blocklist,
        )
        nonce = preview["send_nonce"]
        with mock.patch.object(helper, "_run_osascript", return_value=(0, "", "")):
            result = helper.action_send(
                {"to": "+14155551234", "text": "hello", "send_nonce": nonce},
                None, self.contacts, self.blocklist,
            )
        self.assertIn("sent", result)


if __name__ == "__main__":
    unittest.main()
