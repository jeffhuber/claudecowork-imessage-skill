# Changelog

Notable changes are documented here. Releases use semantic versioning for the
plugin, skill, and helper. The bridge protocol has its own compatibility version
reported by the `status` action.

## 1.1.0 - Unreleased

- Give Claude Cowork an independent LaunchAgent, plist, wrapper, confirmation
  helper, and hardened product root so it can run beside Grok Bot.
- Add native, fail-closed full-message confirmation before every send.
- Restrict outbound recipients to individual phone numbers and conservative
  ASCII email addresses; group identifiers and names are rejected.
- Add private atomic request, response, log, and nonce handling with bounded
  retention and no-follow runtime path validation.
- Use SQLite's online backup API for consistent snapshots of Messages data.
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
