# tests

Unit tests for the `imessage-review` helper. No external dependencies — runs
against the stdlib `unittest` module that ships with any Python 3.

## Running

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

Or run an individual test file:

```bash
python3 -m unittest tests.test_redaction -v
```

The tests import `helper.py` as a module. They do not touch the real
`chat.db`, Contacts, or the launchd agent — everything is pure-Python
input/output testing against the helper's decoder, redaction, and
validation functions.

## What's covered

| File | What it tests |
|------|---------------|
| `test_attributed_body.py` | The hand-rolled typedstream decoder — known-good blobs, malformed input, empty/None, length-prefix variants, silent-failure cases. |
| `test_redaction.py` | The `redact()` pipeline — 2FA codes, credit card numbers, SSNs, and a documented set of known bypasses we have *not* yet closed. |
| `test_validation.py` | Request-parameter validators — bounds checking, type coercion, rejection of malformed input, action whitelist enforcement. |

## What's NOT covered

- The C wrapper (tested manually via the installer smoke test).
- `launchd` triggering (integration test, needs a real Mac).
- Contacts / AddressBook loading (platform-specific; mocked minimally).
- The actual SQL queries against `chat.db` (integration test).

Redaction bypass cases that are currently documented but un-fixed are
marked `expectedFailure`. If you close one of those gaps, flip the test to
a normal `assert` and it becomes a regression guard.
