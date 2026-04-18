"""Tests for request-parameter validators and action whitelist.

The validators are the first line of defense against malformed or
adversarial requests. Each action handler trusts the validator output, so
these bounds checks are load-bearing.
"""
from __future__ import annotations

import unittest

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _helper_loader import helper  # noqa: E402


class ValidateDaysTests(unittest.TestCase):

    def test_valid_int(self):
        self.assertEqual(helper.validate_days(5), 5.0)

    def test_valid_float(self):
        self.assertEqual(helper.validate_days(2.5), 2.5)

    def test_valid_numeric_string(self):
        self.assertEqual(helper.validate_days("7"), 7.0)

    def test_upper_bound_inclusive(self):
        self.assertEqual(helper.validate_days(90), 90.0)

    def test_just_over_upper_bound(self):
        with self.assertRaises(ValueError):
            helper.validate_days(91)

    def test_zero_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_days(0)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_days(-1)

    def test_non_numeric_string_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_days("abc")

    def test_none_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_days(None)

    def test_bool_rejected(self):
        # Python bools are ints, but we explicitly reject them to avoid
        # `True` being interpreted as "1 day".
        with self.assertRaises(ValueError):
            helper.validate_days(True)

    def test_empty_string_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_days("")


class ValidateHoursTests(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(helper.validate_hours(24), 24.0)

    def test_upper_bound(self):
        # MAX_HOURS = 24 * 30 = 720
        self.assertEqual(helper.validate_hours(720), 720.0)

    def test_over_upper(self):
        with self.assertRaises(ValueError):
            helper.validate_hours(721)

    def test_zero_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_hours(0)


class ValidateLimitTests(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(helper.validate_limit(100), 100)

    def test_float_coerced_to_int(self):
        self.assertEqual(helper.validate_limit(5.7), 5)

    def test_upper_bound(self):
        self.assertEqual(helper.validate_limit(500), 500)

    def test_over_upper_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_limit(501)

    def test_zero_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_limit(0)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_limit(-5)


class ValidateSearchTests(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(helper.validate_search("dinner plans"), "dinner plans")

    def test_whitespace_preserved(self):
        # validate_search returns the original string — it does NOT strip.
        # Downstream code depends on seeing the user's exact query.
        self.assertEqual(helper.validate_search("  spaced  "), "  spaced  ")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_search("")

    def test_whitespace_only_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_search("   ")

    def test_non_string_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_search(42)

    def test_none_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_search(None)

    def test_oversized_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_search("x" * 201)

    def test_at_max_length_allowed(self):
        s = "x" * 200
        self.assertEqual(helper.validate_search(s), s)


class ValidateChatTests(unittest.TestCase):

    def test_phone_number(self):
        self.assertEqual(helper.validate_chat("+14155551234"), "+14155551234")

    def test_email(self):
        self.assertEqual(helper.validate_chat("alice@example.com"),
                         "alice@example.com")

    def test_group_chat_id(self):
        self.assertEqual(helper.validate_chat("chat12345678901234567"),
                         "chat12345678901234567")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(helper.validate_chat("  +14155551234  "),
                         "+14155551234")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_chat("")

    def test_whitespace_only_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_chat("   ")

    def test_oversized_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_chat("x" * 201)

    def test_non_string_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate_chat(12345)


class ActionWhitelistTests(unittest.TestCase):
    """Make sure the action whitelist is tight — new actions should be
    deliberate additions, not regressions."""

    EXPECTED_ACTIONS = frozenset({
        "review",
        "search",
        "chat_history",
        "response_stats",
        "contacts_lookup",
        "send_preview",
        "send",
    })

    def test_action_set_is_exactly_expected(self):
        self.assertEqual(set(helper.ACTIONS.keys()), self.EXPECTED_ACTIONS,
                         "ACTIONS whitelist changed unexpectedly — "
                         "update EXPECTED_ACTIONS if this was intentional")

    def test_each_action_is_callable(self):
        for name, fn in helper.ACTIONS.items():
            self.assertTrue(callable(fn),
                            f"ACTIONS[{name!r}] is not callable: {fn!r}")


class RedactionPrivacyFilters(unittest.TestCase):
    """Belt-and-suspenders check that the automated/low-signal filters
    keep doing what the README claims they do."""

    def test_short_code_detection(self):
        # 5-digit "from" numbers are SMS short codes — automation.
        self.assertTrue(helper.is_automated("36246", "hey"))

    def test_rbm_domain_detection(self):
        self.assertTrue(helper.is_automated("notifications@rbm.goog", ""))

    def test_lyft_template_detection(self):
        self.assertTrue(helper.is_automated(
            "+14029519951", "Lyft: Grace requested a ride"))

    def test_real_person_not_automated(self):
        self.assertFalse(helper.is_automated(
            "+14155551234", "Hey, are you around for dinner Saturday?"))

    def test_reaction_prefix_low_signal(self):
        self.assertTrue(helper.is_low_signal('Liked "that\'s awesome"'))

    def test_single_word_ack_low_signal(self):
        self.assertTrue(helper.is_low_signal("thanks"))
        self.assertTrue(helper.is_low_signal("ok!"))

    def test_real_content_not_low_signal(self):
        self.assertFalse(helper.is_low_signal(
            "Did you end up talking to Steve about the term sheet?"))


if __name__ == "__main__":
    unittest.main()
