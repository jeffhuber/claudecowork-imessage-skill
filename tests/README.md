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
| `test_send.py` | `send_preview` and `send` actions — text / service validators, AppleScript string escaping, tempfile lifecycle, blocklist-respect on outbound, `needs_db` short-circuit for send actions. Also covers the v0.4.0+ helper-side send gate: `action_send` refusing missing / bogus / mismatched / replayed nonces, and the preview-then-send round trip. `osascript` is mocked; no real messages go out during the test run. |
| `test_send_gate.py` | The nonce gate in isolation (`send_gate.py`) — mint/consume round-trip, single-use semantics, payload binding, TTL expiry, path-traversal rejection, and the reaper. (v0.4.0+) |
| `test_safety_privacy.py` | Native confirmation behavior, private atomic responses and logs, retention, symlink refusal, runtime directory modes, and LaunchAgent stdio privacy. |
| `test_hardened_architecture.py` | Default-deny read policy, root-owned policy requirements, wrapper component validation, hardened installer flags, and code/runtime root separation. |
| `test_installation_identity.py` | Complete bootstrap packaging, host-specific identities, exact legacy migration, scoped uninstall, and disjoint Claude/Grok resource contracts. |
| `test_reliability.py` | SQLite WAL-consistent snapshots, host-specific status metadata, malformed/oversized/FIFO queue isolation, request-symlink refusal, and doctor failure output. |

## What's NOT covered

- The C wrapper (tested manually via the installer smoke test).
- `launchd` triggering (integration test, needs a real Mac).
- Contacts / AddressBook loading (platform-specific; mocked minimally).
- The actual SQL queries against `chat.db` (integration test).

Redaction bypass cases that are currently documented but un-fixed are
marked `expectedFailure`. If you close one of those gaps, flip the test to
a normal `assert` and it becomes a regression guard.
