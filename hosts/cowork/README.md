# iMessage Plugin for Claude Cowork

Read, search, triage, and send iMessages on macOS from Claude Cowork using the shared iMessage helper.

---

## What You Get

- **Read & triage** your iMessages with natural language ("show me messages from the last day that need a reply")
- **Search** across all your message history ("find any mention of 'quarterly review' in the last month")
- **Send** plain-text iMessages with preview-and-confirm safety ("text Alice: see you at 3")
- **Analyze** response times, conversation patterns, and more
- **Command palette integration:** `/imessage-review:imessages [days]` for one-shot triage

All powered by a lightweight on-device helper that reads your local Messages database and drives AppleScript—no cloud API keys, no GUI automation, no clicking around.

---

## Installation

Claude Cowork uses a **plugin-based installation** model. The iMessage skill is packaged as a `.plugin` file that you install directly in Cowork.

### The Fast Path — From a Release

1. Go to the [Releases page](../../releases/latest) and download `imessage-review.plugin`.
2. In Cowork, drag the `.plugin` file into the app (or use "Install plugin" and point it at the file).
3. Pick a **bridge folder** — any directory on your Mac that Cowork can write to. Example: `~/Documents/imessage-bridge`. Select it as your Cowork workspace.
4. Ask Claude "set up the iMessage helper for this folder." Claude will copy the installer assets into the folder and run `install.sh` for you. (Or do it manually — `cd <bridge folder> && ./install.sh`.)
5. `install.sh` will print the exact path of the compiled wrapper binary and tell you to grant Full Disk Access. Open **System Settings → Privacy & Security → Full Disk Access → + → paste the path → toggle on.**
6. Verify: ask Claude to "triage my iMessages from the last day" or run `/imessage-review:imessages 1`.

### The Source Path — Build It Yourself

```bash
git clone https://github.com/jeffhuber/claudecowork-imessage-skill.git
cd claudecowork-imessage-skill
zip -r imessage-review.plugin . -x "*.DS_Store" "__pycache__/*" "*/__pycache__/*" ".git/*"
```

Then drag `imessage-review.plugin` into Cowork and continue with steps 3–6 above.

---

## What It Does

The plugin gives Claude access to seven helper actions. Claude picks the right one from plain English—you generally don't need to know the action names.

| Action | Ask Claude something like | What it does |
|---|---|---|
| `review` | *"Triage my iMessages from the last 2 days."* | Sorts every thread into `needs reply` / `low priority` / `skipped`, with full text for the needs-reply bucket. |
| `search` | *"Find messages mentioning 'quarterly review' in the last month."* | Substring search across every thread. Scopes by days + result limit. |
| `chat_history` | *"Show me the last 50 messages with the sales-team group chat."* | Pulls recent messages from one conversation. Accepts name, phone, email, or group-chat ID. |
| `response_stats` | *"How fast have I been replying to my manager this week?"* | Avg / median / min / max reply time, plus inbound vs. outbound counts. |
| `contacts_lookup` | *"Look up contacts named 'Smith'."* | Disambiguates by name. Useful before `chat_history` on an ambiguous name. |
| `send_preview` | *(used implicitly by the skill before every send)* | Dry-run of a `send` — validates recipient + body, resolves the contact name, flags blocklisted threads. No osascript call, no chat.db read. |
| `send` | *"Text +14155551234: 'Confirmed for Thursday at 3pm.'"* | Actually delivers the message via AppleScript (`tell application "Messages"`). Always preceded by `send_preview` and explicit user approval. |

**Chained workflows** Claude handles naturally because the read + send actions share a bridge:

- *"Triage the last day, then draft replies to anything actionable."*
- *"Find any mention of 'invoice' in the last 60 days, group by sender."*
- *"Who has the slowest reply time from me this week? Top 5 with stats."*
- *"Text Angel back with a thumbs-up and propose Thursday at 2pm instead."*

---

## How It Works

The Cowork agent runs in a Linux sandbox that can't see `~/Library/Messages`. This plugin installs a `launchd` agent on your Mac that watches for JSON request files in a **bridge folder** (any folder you select as your Cowork workspace). When Claude writes a request file, launchd fires the helper, which reads the Messages database, processes the request, and writes a JSON response back into the same folder—where Claude can then read it.

```
  Cowork (Linux sandbox)                 Your Mac
  ----------------------                 --------
  writes request.json  -->  launchd  -->  helper reads chat.db
                                          writes response.json
  reads response.json  <-----------------/
```

Sending iMessages runs through the **same** bridge: Claude writes a `send` request, the helper shells out to `/usr/bin/osascript` with a short AppleScript that tells Messages.app to send the message via iMessage or SMS. No GUI automation. One subprocess, typically under a second end to end.

---

## Sending

As of v0.3.0, sending is a **first-class helper action** — no Computer Use, no GUI automation. Claude writes a `send` request into the bridge folder, the helper shells out to `/usr/bin/osascript` with a short AppleScript that tells Messages.app to deliver the message. Typical round-trip is under a second.

### How to Use It

Just ask Claude in plain English:

> "Text +14155551234: 'Confirmed for Thursday at 3pm.'"

Claude will:

1. Run a `send_preview` to show you the resolved recipient, service (iMessage vs. SMS), and full text.
2. **Wait for your explicit OK.** Nothing sends until you confirm.
3. Run `send`. The helper writes your text to a UTF-8 tempfile, invokes `osascript`, and deletes the tempfile whether the send succeeds or fails.

### One-Time Permission: Automation → Messages

On the first send, macOS shows an Automation prompt — *"cowork-imessage-helper wants to control Messages"*. Click **OK**. After that, the grant lives under:

**System Settings → Privacy & Security → Automation → cowork-imessage-helper → Messages**

This is a **different permission** from Full Disk Access. FDA lets the helper read `chat.db`; Automation lets it drive Messages.app via AppleScript.

### What Gets Validated Before osascript Even Runs

- Recipient is a phone number / email / group-chat ID (up to 200 chars).
- Text is 1–4000 UTF-8 characters with no C0 control bytes other than `\n`, `\r`, `\t`.
- Service is `iMessage`, `SMS`, or unset (defaults to iMessage).
- Recipient is **not** on `contacts/blocked_chats.txt` — blocklist still applies to outbound as well as inbound.
- **(v0.4.0+)** A fresh, payload-bound `send_nonce` minted by a prior `send_preview` within the last 60 seconds is present on the `send` request. The helper refuses sends without one, sends whose body has been changed after preview, and sends that replay a used nonce. This puts the preview/confirm gate in the helper rather than in the skill prompt — a compromised client can't skip the preview step.

### What It Can't Do

- Attachments / images / stickers / replies-to-specific-message — AppleScript exposes a simple `send <text> to <buddy>` shape. Plain text only.
- Message effects (balloon, confetti, etc.).
- Group-chat creation. You can send *to* an existing group-chat ID, not stand up a new one.

---

## Privacy

### Automatic Redaction

Before returning a response, the helper runs a regex-based redactor that masks:

- 2FA / verification codes (`code`, `passcode`, `OTP`, `one-time` contexts)
- Credit-card-like digit runs (13–19 digits, with or without `-` / space separators)
- US SSN patterns (`NNN-NN-NNNN`)

### Thread-Level Blocklist

You can block entire threads from ever entering Claude's context by adding them to `<bridge folder>/contacts/blocked_chats.txt` (phone numbers, emails, or group-chat IDs — one per line). Blocked threads are dropped before the redactor even runs.

### Consent — The Thing Nobody Else on the Thread Agreed To

When you use this plugin, you're piping both sides of your conversations — including messages you received from other people — into a commercial LLM (Claude). Those people didn't consent to that, and in many cases they'd reasonably object if they knew. This is an unavoidable property of any "read my messages" tool, but it's worth sitting with before you run this every morning as a habit.

**Strongly consider preemptively blocklisting** any thread that contains messages you would not want an LLM to read, including:

- Therapists, counselors, clergy, medical providers
- Attorneys and anyone else you have privileged communication with
- Financial advisors, accountants
- Family members during a dispute or sensitive life event
- Minors (your kids, your kids' friends, babysitters, etc.)
- Anyone who has explicitly told you "please keep this between us"
- Journalists or sources, if you're one of those people
- Anyone in a jurisdiction with two-party-consent recording laws where running their messages through a third party might be an issue

Adding a chat to `contacts/blocked_chats.txt` is a one-line operation and is enforced *before* redaction — those messages never reach Claude at all.

---

## Requirements

- macOS (the helper is Apple-specific — SQLite + launchd + Contacts.app + osascript)
- Xcode Command Line Tools (`xcode-select --install`) — for `clang` and `codesign` during install
- Python 3 (uses `/usr/bin/python3` if available, otherwise `$PATH`)
- `/usr/bin/osascript` — ships with macOS, used for sending

---

## Known Limitations

Being upfront about what this tool does and doesn't do. None of these are reasons to avoid using it — they're reasons to use it with your eyes open.

### Redaction Is Regex-Based and Has Documented Gaps

The redactor catches the common 2FA / card / SSN cases but is not a DLP product. Known bypasses (all have regression tests under `tests/test_redaction.py::RedactionKnownBypasses`, marked `@expectedFailure`):

- Dot-separated credit cards (`4111.1111.1111.1111`)
- PIN-labelled codes (`Your PIN is 4829` — "PIN" isn't in the keyword list)
- Slash-separated SSNs (`123/45/6789`)
- Bare verification codes with no keyword (`839201 to confirm it's you`)
- API keys (Stripe `sk_live_*`, GitHub tokens, OpenAI keys, etc.)
- Bank account / routing numbers (below the 13-digit card floor)
- Home addresses
- Dates of birth

If you close one of these gaps, flip the `@unittest.expectedFailure` decorator off in the matching test and it becomes a regression guard.

**Implication:** assume sensitive content will occasionally slip through. The thread-level blocklist is the reliable filter; the regex is a second line of defense, not the first.

### Full Disk Access Grant Is Tied to a Specific Binary Hash

The grant is attached to the ad-hoc-signed helper's **CDHash**, not its path. That means:

- Re-running the installer against a **bit-identical** source rebuilds the same CDHash and the grant carries over.
- Changing the C source, the Python, or even a compiler version *can* produce a different CDHash, at which point macOS will silently drop requests until you re-grant FDA to the new binary.
- macOS can also invalidate the grant on its own — major OS upgrades, Spotlight reindex weirdness, or TCC resets have all been reported.

**Symptom:** the helper stops responding, requests pile up unprocessed in the bridge folder. **Fix:** re-open System Settings → Privacy & Security → Full Disk Access, remove the old entry, re-add the binary at the path the installer prints.

### Privacy Tradeoff: Messages Flow Through a Commercial LLM

This is not a local LLM pipeline. Every thread you surface flows through Anthropic's API as part of the Claude context window and is subject to Anthropic's data handling and retention policies, not yours. If that's not acceptable for a specific conversation, blocklist it (see above).

### macOS-Only, and Leans on Private-ish Schemas

`chat.db` and `AddressBook-v22.abcddb` are Apple-internal SQLite schemas with no stability guarantee. They've been stable for years, but a future macOS release could rename a column and break the helper until someone patches the queries. Same applies to the `attributedBody` typedstream format that the decoder in `helper.py` reverse-engineers.

### Sending Relies on AppleScript + the Messages.app Automation Grant

Sending goes through the helper, which calls `/usr/bin/osascript` with a short AppleScript `tell application "Messages"` block. That means:

- The first send triggers a macOS Automation prompt — you have to click **OK** to let the helper control Messages.app. The grant lives under System Settings → Privacy & Security → Automation.
- AppleScript will happily send to a `buddy` handle that doesn't have iMessage coverage; the helper does minimal validation beyond "is-it-a-string". If you send to a number that can't receive iMessage and you picked `service: iMessage`, the osascript call errors out and nothing is delivered — switch to `service: SMS`.
- There's no "sent successfully to the network" confirmation. The helper only confirms that osascript returned 0. If the recipient blocks you or the network is down, iMessage will show the red ! bubble in Messages.app, but the helper won't know.

The tradeoff vs. the previous Computer-Use path is speed (sub-second vs. 5–15s), reliability (no pixel races), and the same "preview + explicit user approval before the send request" safety model baked into the skill instructions — now enforced helper-side (v0.4.0+) via a single-use nonce, so the preview step can't be skipped even by a compromised client.

---

## Uninstall

Run `./uninstall.sh` from the bridge folder. This removes the launchd agent. Files and the Full Disk Access grant are left in place — remove those manually if you want a full teardown.

---

## References

- **Plugin skill file:** `skills/imessage-review/SKILL.md` (teaches Claude the protocol)
- **Full protocol documentation:** `docs/PROTOCOL.md`
- **Security details:** `SECURITY.md` (in the repo root)
- **Source & releases:** [github.com/jeffhuber/claudecowork-imessage-skill](https://github.com/jeffhuber/claudecowork-imessage-skill)

---

## License

MIT. See `LICENSE` in the repo root.
