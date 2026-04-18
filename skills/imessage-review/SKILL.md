---
name: imessage-review
description: >
  This skill should be used when the user mentions "iMessages", "my messages",
  "text messages", asks to "triage iMessages", "find messages that need a
  reply", "search my iMessages", "show my chat history with", or wants
  response-time stats for a contact. Also covers sending a plain-text
  iMessage. macOS only — uses an on-device launchd helper to query the
  Messages SQLite database, and AppleScript (osascript) via the same helper
  to send outbound messages.
version: 0.3.0
---

# iMessage on macOS — Cowork-native

## When to use

Use this skill when the user asks to:

- Review / triage recent iMessages or SMS.
- Find messages that still need a response.
- Search history for a topic, person, or phrase.
- Pull a specific conversation's recent messages.
- Compute response-time statistics (e.g. "average reply time to Angel over the last 24 hours").
- Send a plain-text iMessage to an existing contact.

## Architecture at a glance

```
  Cowork agent (Linux sandbox)             ~/Library (the user's Mac)
  ----------------------------             -------------------------
  Writes request-<id>.json   --> launchd watches control/requests/ -->
  Reads  response-<id>.json  <-- cowork-imessage-helper (wrapper)  -->
                                 helper.py (FDA-granted, read-only
                                 copy of chat.db + AddressBook)
```

The Cowork sandbox cannot read `~/Library/Messages/chat.db` directly — its
Bash tool runs in a Linux VM with no view of the Mac filesystem. A launchd
agent bridges the two sides: Claude drops a JSON request into the selected
Cowork folder, launchd fires a tiny signed wrapper binary that has Full Disk
Access, the wrapper execs `helper.py`, and helper writes the JSON response
back into the same folder where Claude can read it.

Sending goes through the **same** request/response bridge. Claude writes a
`send_preview` or `send` request, the helper calls `osascript` to drive
Messages.app via AppleScript, and the result comes back as JSON. No GUI
automation, no Computer Use clicks — just a short-lived subprocess.

## Prerequisites — one-time setup

This plugin ships the helper source and install scripts bundled inside the
skill directory (alongside this `SKILL.md`):

- `install.sh` / `uninstall.sh`
- `com.user.cowork-imessage.plist.template`
- `bin/cowork_imessage_helper.c` (wrapper source)
- `bin/helper.py` (Python worker)

The user runs a one-time install into the Cowork folder they want to use as
the request/response bridge. Order of operations the first time a user asks
Claude to read iMessages:

1. Verify the user has selected a Cowork folder. If not, tell them to pick
   one (it will hold `control/` and `bin/`). Call it the "bridge folder".
2. Check whether `<bridge folder>/bin/cowork-imessage-helper` exists. If
   missing, the helper isn't installed. Guide the user through these steps:

   a. Copy the plugin's install assets to the bridge folder:

      ```bash
      SRC="$(dirname "$(dirname "$0")")"  # path to this skill dir
      DEST="<bridge folder>"
      cp "$SRC/install.sh" "$SRC/uninstall.sh" \
         "$SRC/com.user.cowork-imessage.plist.template" "$DEST/"
      mkdir -p "$DEST/bin"
      cp "$SRC/bin/cowork_imessage_helper.c" "$SRC/bin/helper.py" "$DEST/bin/"
      ```

   b. In Terminal: `cd <bridge folder> && chmod +x install.sh && ./install.sh`
   c. When install.sh prints FDA instructions, guide the user through:
      System Settings → Privacy & Security → Full Disk Access → + →
      paste the path printed (e.g. `<bridge folder>/bin/cowork-imessage-helper`).

3. Verify: `<bridge folder>/control/{requests,responses}/` and `log.txt`
   exist, and `~/Library/LaunchAgents/com.user.cowork-imessage.plist`
   exists.

If any verification fails, tell the user exactly which step broke and show
the relevant line from `control/log.txt`.

## Invoking the helper (read/analyze actions)

Write a JSON file to `<bridge folder>/control/requests/request-<id>.json`.
launchd will fire the helper within ~1 second (WatchPaths has a 1s
ThrottleInterval). Then poll
`<bridge folder>/control/responses/response-<id>.json` until it appears —
typically 2–5s total including the chat.db copy.

Use a UUID or timestamp for `<id>`. Always set `id` inside the request body
to the same string.

Whitelisted actions (anything else is rejected):

### `review` — triage recent messages

```json
{"id": "abc", "action": "review", "params": {"days": 2}}
```

Response has three buckets: `needs_reply`, `low_priority`, and `skip_summary`
(summary only — skip-bucket message text is not returned).

### `search` — find messages by substring

```json
{"id": "abc", "action": "search",
 "params": {"term": "dinner plans", "days": 30, "limit": 100}}
```

### `chat_history` — recent messages in one thread

```json
{"id": "abc", "action": "chat_history",
 "params": {"chat": "Angel Vossough", "days": 14, "limit": 100}}
```

`chat` accepts a contact name (resolved via Contacts.app), a phone number
(any format — the helper matches the last 10 digits), or an email address.

### `response_stats` — average reply time to one contact

```json
{"id": "abc", "action": "response_stats",
 "params": {"chat": "Angel Vossough", "hours": 24}}
```

Returns `sample_size`, `avg_seconds`, `avg_human` (e.g. `"18.3m"`),
`median_seconds`, `min`/`max`, and inbound/outbound counts.

### `contacts_lookup` — find matching contacts

```json
{"id": "abc", "action": "contacts_lookup", "params": {"name": "Angel"}}
```

### `send_preview` — dry-run a send (no osascript, no chat.db)

```json
{"id": "abc", "action": "send_preview",
 "params": {"to": "+14155551234", "text": "Confirmed for 3pm.",
            "service": "iMessage"}}
```

Response includes the validated recipient, the resolved contact name (if any),
the service, the text and its length, and whether the thread is on the
blocklist. `send_preview` is declarative — it does *not* touch chat.db and
does *not* send anything. Use it to confirm with the user before calling
`send`.

### `send` — actually send the message

```json
{"id": "abc", "action": "send",
 "params": {"to": "+14155551234", "text": "Confirmed for 3pm.",
            "service": "iMessage"}}
```

The helper writes `text` to a temporary UTF-8 file, shells out to
`/usr/bin/osascript` with a short AppleScript that reads the file and tells
Messages.app to send it to the addressed buddy on the requested service
(`iMessage` or `SMS`). The tempfile is always removed, even on failure.

Response on success includes `sent: {to, resolved_name, service,
text_length, sent_at}`. On failure, the helper returns an error with the
osascript stderr — typical causes are missing Automation permission for
Messages (see "Sending messages" below) or a recipient that isn't
reachable on the chosen service.

**Refusal rules baked into the helper** — no way for Claude to override:
- Text must be 1–4000 chars and contain no C0 control characters other
  than `\n`, `\r`, `\t`.
- `service` must be `"iMessage"`, `"SMS"`, or omitted (defaults to iMessage).
- If the recipient matches an entry in `contacts/blocked_chats.txt`, `send`
  raises `ValueError` before calling osascript.

## Example request flow

```python
# Pseudocode — actual tool calls are Write + Bash/Read against the
# Cowork-selected bridge folder, which is mounted at a path like
#   /sessions/<session-id>/mnt/<folder-name>
import json, uuid, time, pathlib

root = pathlib.Path("<bridge folder>")
req_id = uuid.uuid4().hex[:12]
(root / "control" / "requests" / f"request-{req_id}.json").write_text(
    json.dumps({"id": req_id, "action": "review", "params": {"days": 2}})
)

resp = root / "control" / "responses" / f"response-{req_id}.json"
for _ in range(30):
    if resp.exists():
        break
    time.sleep(0.5)
data = json.loads(resp.read_text())
```

## Sending messages

Sending is an action on the helper, same bridge as read actions. The helper
uses AppleScript via `/usr/bin/osascript` to tell Messages.app to send the
message — no GUI clicks, no Computer Use, just a subprocess that returns in
under a second on average.

**Recommended flow every time — preview, confirm, then send:**

1. Resolve the recipient. If the user said a name, run `contacts_lookup`
   first. If there are multiple matches, surface them and ask. Use a raw
   phone number (any format — last 10 digits match) or email if the user
   prefers that.
2. Issue a `send_preview` request. Show the user the resolved recipient
   name, the service (iMessage / SMS), the full text, and `text_length`.
3. **Wait for explicit user approval.** If the preview shows `blocked: true`,
   tell the user and stop — don't prompt for approval to send anyway.
4. Issue the `send` request. Surface `sent.sent_at` and the resolved name
   back to the user as confirmation.

### Why the helper instead of computer-use?

Computer-use driving Messages.app was slow (5–15s for the full click-type-
Return dance), flaky (autocomplete races, Send-as-SMS sheets, modal popups),
and inherently imprecise (pixel-level clicks on a UI that can change
between macOS releases). AppleScript's `tell application "Messages"` API
takes a recipient + service + body and dispatches the message directly. For
the same confirmation-safety model, we gate it behind `send_preview` +
explicit user OK before calling `send`.

### Automation permission (one-time, separate from Full Disk Access)

The first time the helper calls `osascript` to send via Messages, macOS
will show an Automation prompt: "cowork-imessage-helper wants to control
Messages." Click **OK**. After that, the grant lives under:

  System Settings → Privacy & Security → Automation →
    cowork-imessage-helper → Messages (toggle on)

If the wrapper binary is rebuilt with a different CDHash, the grant needs
to be removed and re-added (same as Full Disk Access).

## Common pitfalls

- **FDA not granted yet.** First request returns `sqlite3.OperationalError:
  unable to open database file` in `log.txt`. Tell the user to grant FDA to
  the wrapper binary (exact path is in `install.sh` output).
- **Wrapper re-signed.** If the user rebuilt the wrapper after a content
  change, the FDA grant needs to be removed and re-added (System Settings
  updates the identity automatically, but a stale grant toggled ON won't
  apply).
- **Ambiguous contact name.** `response_stats` with `chat: "Alex"` resolves
  via the first contact whose name contains "Alex" — may not be the one
  intended. Fall back to a phone number if the user has multiple Alexes.
- **Group chats.** `chat_identifier` for groups looks like `chat1234567…`.
  The `chat_history` action accepts these directly if you already have one
  from a prior `review` response.
- **Messages still decoding as empty.** The `attributedBody` parser is
  heuristic. If a thread's messages come back blank, check `log.txt` —
  the helper logs the first 64 bytes of each unparseable blob.
- **Wrong folder selected.** If the user selects a different Cowork folder
  after installing, launchd is still watching the original bridge folder.
  Re-run `install.sh` from the new folder to point launchd at it.

## Redaction and privacy

The helper redacts before writing the response:

- 2FA / verification codes near words like "code", "verification", "OTP".
- Credit-card-like digit runs (13–19 digits).
- US SSN patterns.

Chats listed in `contacts/blocked_chats.txt` are dropped entirely — their
text never enters the response JSON, which means it never enters Claude's
context window. Users should add therapist / attorney / financial advisor
threads here.

## Files shipped with this skill

| Path | Role |
|------|------|
| `SKILL.md` | This file. |
| `install.sh` | One-time setup: builds + signs wrapper, installs plist, bootstraps launchd. |
| `uninstall.sh` | Removes the launchd agent. Leaves files + FDA grant. |
| `com.user.cowork-imessage.plist.template` | launchd agent template. Filled in by `install.sh` and copied to `~/Library/LaunchAgents/`. |
| `bin/cowork_imessage_helper.c` | Tiny hardened wrapper. FDA is granted to this. Ignores argv, sanitizes environment, execs helper.py. |
| `bin/helper.py` | Python helper. Scans `control/requests/`, dispatches actions, writes `control/responses/response-*.json`. |

## Files created at the user's bridge folder (after install)

| Path | Role |
|------|------|
| `contacts/blocked_chats.txt` | User-maintained blocklist of sensitive chats. |
| `control/requests/` | Agent writes request JSON here. Watched by launchd. |
| `control/responses/` | Helper writes response JSON here. Agent reads. |
| `control/log.txt` | Helper stderr + logging. First place to check when debugging. |
| `bin/cowork-imessage-helper` | Compiled, ad-hoc signed wrapper (the FDA target). |
