"""Tests for the response-egress redaction layer.

Two categories:

  1. Should-redact tests — these MUST pass. If one of these starts failing,
     we've regressed on a known-covered redaction class.

  2. Known-bypass tests (expectedFailure) — these document real gaps in the
     current regex-based redactor. They exist so the scope of the leak is
     written down in code, not just in a README somewhere. If you close a
     gap, flip the `@unittest.expectedFailure` into a regular assertion
     and the test becomes a regression guard.

Redaction is intentionally conservative on the "should redact" side (we
cover the common cases) and intentionally transparent about the gaps. This
module is the contract.
"""
from __future__ import annotations

import unittest

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _helper_loader import helper  # noqa: E402


class RedactionShouldCatch(unittest.TestCase):
    """Cases the current redactor IS expected to handle."""

    # ---- 2FA / verification codes ----------------------------------------

    def test_verification_code_prefix(self):
        out = helper.redact("Your verification code is 123456")
        self.assertIn("[REDACTED-2FA]", out)
        self.assertNotIn("123456", out)

    def test_code_colon_form(self):
        out = helper.redact("Code: 789012")
        self.assertIn("[REDACTED-2FA]", out)
        self.assertNotIn("789012", out)

    def test_otp_prefix(self):
        out = helper.redact("OTP 4829 expires in 5 min")
        self.assertIn("[REDACTED-2FA]", out)
        self.assertNotIn("4829", out)

    def test_code_suffix_form(self):
        out = helper.redact("1234 is your code")
        self.assertIn("[REDACTED-2FA]", out)
        self.assertNotIn("1234", out)

    def test_passcode_keyword(self):
        out = helper.redact("Use passcode 556677 to log in")
        self.assertIn("[REDACTED-2FA]", out)
        self.assertNotIn("556677", out)

    def test_one_time_hyphenated(self):
        out = helper.redact("Your one-time code: 998877")
        self.assertIn("[REDACTED-2FA]", out)
        self.assertNotIn("998877", out)

    # ---- credit card numbers ---------------------------------------------

    def test_card_dashed(self):
        out = helper.redact("Card on file: 4111-1111-1111-1111")
        self.assertIn("[REDACTED-CARD]", out)
        self.assertNotIn("4111", out)

    def test_card_spaced(self):
        out = helper.redact("Charged 4111 1111 1111 1111 for dinner")
        self.assertIn("[REDACTED-CARD]", out)

    def test_card_no_separator(self):
        out = helper.redact("CC 4111111111111111")
        self.assertIn("[REDACTED-CARD]", out)

    def test_amex_15_digit(self):
        # 15-digit Amex should still match the 13-19 range.
        out = helper.redact("Amex: 3782 822463 10005")
        self.assertIn("[REDACTED-CARD]", out)

    # ---- SSN -------------------------------------------------------------

    def test_ssn_hyphenated(self):
        out = helper.redact("SSN 123-45-6789 for the W-9")
        self.assertIn("[REDACTED-SSN]", out)
        self.assertNotIn("123-45-6789", out)

    # ---- non-sensitive content should be untouched -----------------------

    def test_plain_chat_untouched(self):
        original = "See you at 6:30 at the usual spot"
        self.assertEqual(helper.redact(original), original)

    def test_short_digit_run_not_redacted_as_card(self):
        original = "Order #12345 is ready"
        self.assertEqual(helper.redact(original), original)

    def test_phone_number_not_redacted(self):
        # US phone numbers are 10 digits — below the 13-digit card threshold.
        original = "Call me at 415-555-0123"
        self.assertEqual(helper.redact(original), original)

    def test_empty_string(self):
        self.assertEqual(helper.redact(""), "")

    def test_none_returns_none(self):
        # redact() is supposed to be tolerant of falsy input.
        self.assertEqual(helper.redact(None), None)


class RedactionKnownBypasses(unittest.TestCase):
    """Documented gaps in the regex-based redactor.

    Each test shows a real-world input that will leak through. If you
    broaden the regex to cover one, flip the decorator off and it becomes
    a regression guard.
    """

    @unittest.expectedFailure
    def test_dot_separated_card_slips_through(self):
        # _CARD_RE uses `[ -]?` and does NOT cover dots.
        out = helper.redact("Amex 4111.1111.1111.1111")
        self.assertIn("[REDACTED-CARD]", out)

    @unittest.expectedFailure
    def test_pin_keyword_not_covered(self):
        # "PIN" is not in the 2FA keyword list; this 4-digit code leaks.
        out = helper.redact("Your PIN is 4829")
        self.assertIn("[REDACTED-2FA]", out)

    @unittest.expectedFailure
    def test_slash_separated_ssn(self):
        # SSN regex requires hyphens; slashes leak.
        out = helper.redact("SSN 123/45/6789")
        self.assertIn("[REDACTED-SSN]", out)

    @unittest.expectedFailure
    def test_bare_verification_code_no_keyword(self):
        # Some SMS senders omit the word "code" or "verification" entirely.
        out = helper.redact("Hi Alex — 839201 to confirm it's you")
        self.assertIn("[REDACTED-2FA]", out)

    @unittest.expectedFailure
    def test_api_key_not_redacted(self):
        # Stripe / GitHub / OpenAI API keys are not covered at all.
        out = helper.redact("Here's the key: sk_live_abcdEFGH1234ijkl")
        self.assertNotIn("sk_live_abcdEFGH1234ijkl", out)

    @unittest.expectedFailure
    def test_bank_account_not_redacted(self):
        # 12-digit account numbers fall below the 13-digit card floor.
        out = helper.redact("Account 123456789012 ABA 021000021")
        self.assertIn("[REDACTED", out)

    @unittest.expectedFailure
    def test_home_address_not_redacted(self):
        # Addresses are not redacted at all.
        out = helper.redact("I live at 123 Main St, Apt 5B, Palo Alto")
        self.assertNotIn("123 Main St", out)

    @unittest.expectedFailure
    def test_date_of_birth_not_redacted(self):
        # DOBs leak through.
        out = helper.redact("DOB: 04/17/1985")
        self.assertNotIn("04/17/1985", out)


if __name__ == "__main__":
    unittest.main()
