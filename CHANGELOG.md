# Changelog

Notable changes are documented here. Releases use semantic versioning for the
plugin, skill, and helper. The bridge protocol has its own compatibility version
reported by the `status` action.

## Unreleased

- Harden hardened-install Python selection by validating interpreter ownership
  and path permissions before executing a compatibility probe.
- Report shell-only `chat.db` access accurately in `doctor.py`; wrapper Full
  Disk Access remains verified by the smoke test.
- Pin setup-python by commit and prevent release checkout credential persistence.

## 1.2.1 - 2026-08-13

- Select and validate one supported Python interpreter for installer tasks and
  the FDA wrapper, even when an older `python3` appears first on `PATH`.
- Fail closed on an invalid `IMESSAGE_PYTHON`; hardened installs require a
  root-owned interpreter path that another user process cannot replace.
- Validate one deterministic ISO-dated changelog heading during release checks.

## 1.2.0 - 2026-08-13

- Clarify standard and hardened installation as an explicit threat-model choice.
- Add a deterministic shared-core manifest and CI check for security parity
  with the Grok Bot and ChatGPT/Codex sibling repositories.
- Fail closed when `IMESSAGE_BRIDGE_DIR` is empty (the retired `~/cowork-imessage`
  default no longer falls through silently).
- Document standard installation as the default-recommended posture in README;
  hardened remains available for organizations requiring defense-in-depth.
- Bridge protocol remains at 1.1 (no changes).

## 1.1.1 - 2026-08-12

- Rename wrapper source from `cowork_imessage_helper.c` to `imessage_helper.c`.
- Export `IMESSAGE_BRIDGE_DIR`; keep `COWORK_IMESSAGE_BRIDGE_DIR` as a one-release alias.
- Refuse the retired `~/cowork-imessage` send-gate default; `COWORK_IMESSAGE_BRIDGE_DIR` is now required.
- Document three-host coexistence (Grok Bot, Claude Cowork, ChatGPT/Codex).
- Lead with standard install in README (hardened is optional, not default-recommended).
- Add native send-confirmation dialog screenshot to documentation.

## 1.1.0 - 2026-08-12

- Give Claude Cowork an independent LaunchAgent, plist, wrapper, confirmation
  helper, and hardened product root so it can run beside Grok Bot.
- Add native, fail-closed full-message confirmation before every send.
- Restrict outbound recipients to individual phone numbers and conservative
  ASCII email addresses; group identifiers and names are rejected.
- Add private atomic request, response, log, and nonce handling with bounded
  retention and no-follow runtime path validation.
- Use SQLite's online backup API for consistent snapshots of Messages data.
- Open completed Messages snapshots as immutable, read-only databases so
  WAL-marked snapshots do not require writable `-wal` or `-shm` sidecars.
- Add `status`, a non-destructive doctor, protocol compatibility reporting,
  tests, CI, and checksummed source/plugin release artifacts.
- Add an optional hardened install with root-owned executable code, wrapper
  validation of every loaded component, and a root-owned default-deny read
  allowlist.
- Migrate the old shared LaunchAgent only when its plist points to the exact
  Claude installation being upgraded.

## 0.4.0 - 2026-04-18

- Add a helper-side, single-use nonce gate bound to the exact send preview.

## 0.3.0 - 2026-04-18

- Add plain-text iMessage and SMS sending through Messages AppleScript.

## 0.2.0 - 2026-04-17

- Initial public read, search, triage, redaction, and privacy controls.
