# iMessage Skill for Grok Bot

Read, search, triage, and send iMessages on macOS from Grok Bot using the shared iMessage helper.

---

## What You Get

- **Read & triage** your iMessages with natural language ("show me messages from the last day that need a reply")
- **Search** across all your message history ("find any mention of 'quarterly review' in the last month")
- **Send** plain-text iMessages with preview-and-confirm safety ("text Alice: see you at 3")
- **Analyze** response times, conversation patterns, and more

All powered by a lightweight on-device helper that reads your local Messages database and drives AppleScript—no cloud API keys, no GUI automation, no clicking around.

---

## Prerequisites

- **macOS** (the helper is Apple-specific—SQLite + launchd + Contacts.app + osascript)
- **Xcode Command Line Tools** (`xcode-select --install`) — for building the helper wrapper
- **Python 3** (uses `/usr/bin/python3` if available, otherwise `$PATH`)
- **Grok Bot** with shell/command execution support (to write request files and read responses on your Mac)

---

## Installation

### Step 1: Clone or Download This Repo

```bash
git clone https://github.com/jeffhuber/claudecowork-imessage-skill.git
cd claudecowork-imessage-skill
```

Or download the [latest release](../../releases/latest) and unzip it.

---

### Step 2: Choose a Bridge Folder

Pick any directory on your Mac where you want the helper to live. This folder will hold the request/response bridge and the helper binaries. Examples:

- `~/imessage-bridge`
- `~/Documents/grok-imessage`
- `~/grok-bot-workspace/imessage`

**Important:** Remember this path—you'll need to tell Grok Bot where it is later.

```bash
mkdir -p ~/imessage-bridge
cd ~/imessage-bridge
```

---

### Step 3: Copy Install Assets

From the cloned repo, copy the install scripts and helper source to your bridge folder:

```bash
REPO_PATH="<path-to-cloned-repo>"  # e.g., ~/claudecowork-imessage-skill
cp "$REPO_PATH/skills/imessage-review/install.sh" \
   "$REPO_PATH/skills/imessage-review/uninstall.sh" \
   "$REPO_PATH/skills/imessage-review/com.user.cowork-imessage.plist.template" \
   ~/imessage-bridge/

mkdir -p ~/imessage-bridge/bin
cp "$REPO_PATH/skills/imessage-review/bin/cowork_imessage_helper.c" \
   "$REPO_PATH/skills/imessage-review/bin/helper.py" \
   "$REPO_PATH/skills/imessage-review/bin/send_gate.py" \
   ~/imessage-bridge/bin/
```

---

### Step 4: Run the Installer

```bash
cd ~/imessage-bridge
chmod +x install.sh
./install.sh
```

The installer will:

1. Build and sign the C wrapper (`bin/cowork-imessage-helper`)
2. Set up the bridge directory structure (`control/requests/`, `control/responses/`, `contacts/`)
3. Install a launchd agent to watch for request files
4. Print the exact path you need to grant Full Disk Access to

**Example output:**

```
cowork-imessage installer
  install root : /Users/you/imessage-bridge
  helper.py    : /Users/you/imessage-bridge/bin/helper.py
  wrapper bin  : /Users/you/imessage-bridge/bin/cowork-imessage-helper
  launchd plist: /Users/you/Library/LaunchAgents/com.user.cowork-imessage.plist

  created /Users/you/imessage-bridge/contacts/blocked_chats.txt (empty)
  chmod 500 /Users/you/imessage-bridge/bin/helper.py
Building wrapper binary...
  built /Users/you/imessage-bridge/bin/cowork-imessage-helper
  ad-hoc signed /Users/you/imessage-bridge/bin/cowork-imessage-helper
  cdhash: 1a2b3c4d...
  wrote /Users/you/Library/LaunchAgents/com.user.cowork-imessage.plist
  launchd agent bootstrapped (com.user.cowork-imessage)

Install complete.

ONE MANUAL STEP REMAINS: grant Full Disk Access to the wrapper.

  1. Open: System Settings -> Privacy & Security -> Full Disk Access
  2. Click the + button, then press Cmd-Shift-G and paste:

       /Users/you/imessage-bridge/bin/cowork-imessage-helper

  3. Select 'cowork-imessage-helper' and make sure its toggle is ON.
  4. (If prompted to quit and reopen anything, just click 'Later'.)
```

---

### Step 5: Grant Full Disk Access

Open **System Settings → Privacy & Security → Full Disk Access**.

1. Click the **+** button.
2. Press **Cmd-Shift-G** and paste the path printed by `install.sh` (e.g., `/Users/you/imessage-bridge/bin/cowork-imessage-helper`).
3. Select the `cowork-imessage-helper` binary and ensure its toggle is **ON**.

**Why?** Full Disk Access lets the helper read `~/Library/Messages/chat.db`, which is where iMessage stores your conversations.

---

### Step 6: Enable the Skill in Grok Bot

How you enable the skill depends on your Grok Bot setup. Typical paths:

- **If Grok Bot supports loading Markdown skill files:** Point it at `<repo>/hosts/grok-bot/SKILL.md` or copy the file into Grok Bot's skills directory.
- **If Grok Bot uses a configuration file:** Add an entry for this skill with the path to `SKILL.md`.
- **If Grok Bot has a UI for managing skills:** Import or enable the skill from the UI.

Consult your Grok Bot documentation for the exact steps.

---

### Step 7: Tell Grok Bot Where the Bridge Folder Is

The first time you ask Grok Bot to read or send an iMessage, it will need to know where your bridge folder is located. You'll need to provide the path you chose in Step 2.

**Example conversation:**

> **You:** "Triage my iMessages from the last day."
>
> **Grok Bot:** "To read your iMessages, I need to know where you installed the iMessage helper. What folder did you run `install.sh` in?"
>
> **You:** "`~/imessage-bridge`"
>
> **Grok Bot:** [verifies the path, then proceeds with the triage]

Grok Bot should remember the path for the rest of the conversation.

---

### Step 8 (Optional): Test It

Ask Grok Bot to:

- "Triage my iMessages from the last 2 days."
- "Search my messages for 'dinner plans' in the last month."
- "Show me my chat history with Alice."

If anything fails, check `~/imessage-bridge/control/log.txt` for errors.

---

## Sending iMessages

Sending is supported out of the box. The first time you ask Grok Bot to send a message, macOS will prompt:

> "cowork-imessage-helper wants to control Messages."

Click **OK**. After that, the grant lives under:

**System Settings → Privacy & Security → Automation → cowork-imessage-helper → Messages**

This is a **separate permission** from Full Disk Access. FDA lets the helper read `chat.db`; Automation lets it drive Messages.app via AppleScript.

**Recommended workflow:**

1. Ask Grok Bot to send a message (e.g., "Text +14155551234: 'Confirmed for Thursday at 3pm.'")
2. Grok Bot will show you a preview: recipient, service (iMessage/SMS), full text, and length.
3. **Approve explicitly** before it sends.
4. The helper sends via AppleScript—typically under a second end to end.

**What sending can't do:**
- Attachments, images, stickers, audio, or Tapback reactions (text only)
- Message effects (balloons, confetti, etc.)
- Group-chat creation (can send *to* an existing group, but not stand one up)

---

## Privacy & Blocklist

### Automatic Redaction

Before returning a response, the helper runs a regex-based redactor that masks:

- 2FA / verification codes (`code`, `passcode`, `OTP`, `one-time` contexts)
- Credit-card-like digit runs (13–19 digits)
- US SSN patterns (`NNN-NN-NNNN`)

**Known gaps** (see `docs/PROTOCOL.md`):
- Dot-separated credit cards
- PIN-labelled codes
- API keys (Stripe, GitHub, OpenAI tokens)
- Bank account numbers
- Home addresses

The thread-level blocklist (below) is the reliable filter; redaction is a second line of defense.

### Thread-Level Blocklist

Block entire threads from ever entering Grok Bot's context by adding them to:

```
~/imessage-bridge/contacts/blocked_chats.txt
```

Format: one entry per line. Lines starting with `#` are ignored.

**Matches:**
- **Phone numbers:** last 10 digits compared (e.g., `+1-555-123-4567`, `5551234567`, `(555) 123-4567` all match)
- **Email addresses:** full case-insensitive match
- **Group chat IDs:** anything starting with `chat` or containing a distinctive substring

**Example:**
```
# Therapist
+15551234567

# Attorney
lawyer@example.com

# Family group chat
chat123456789
```

Blocked threads are dropped **before** the redactor even runs—their text never enters Grok Bot's context.

### Consent — The Thing Nobody Else Agreed To

When you use this skill, you're piping both sides of your conversations—including messages you received from other people—into an AI assistant. Those people didn't consent to that, and in many cases they'd reasonably object if they knew.

**Strongly consider preemptively blocklisting** any thread that contains messages you would not want an AI to read, including:

- Therapists, counselors, clergy, medical providers
- Attorneys and anyone else you have privileged communication with
- Financial advisors, accountants
- Family members during a dispute or sensitive life event
- Minors (your kids, your kids' friends, babysitters, etc.)
- Anyone who has explicitly told you "please keep this between us"
- Journalists or sources, if you're one of those people
- Anyone in a jurisdiction with two-party-consent recording laws

Adding a chat to the blocklist is a one-line operation and is enforced *before* redaction—those messages never reach Grok Bot at all.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Requests pile up in `control/requests/`, no responses | FDA not granted yet | Grant FDA to the wrapper binary (path printed by `install.sh`) |
| `sqlite3.OperationalError: unable to open database file` in `log.txt` | FDA not granted, or grant stale | Re-add the wrapper in System Settings → Full Disk Access |
| First send fails with Automation prompt | macOS needs Automation permission | Click **OK** on the prompt; future sends will work |
| `send gate: missing nonce` | `send` called without prior `send_preview` | Always call `send_preview` first (Grok Bot should handle this automatically) |
| Messages decode as empty | `attributedBody` parser failed | Check `control/log.txt`—helper logs the first 64 bytes of unparseable blobs |

Check `~/imessage-bridge/control/log.txt` first when debugging. It contains helper stderr and logging.

---

## Uninstall

```bash
cd ~/imessage-bridge
./uninstall.sh
```

This removes the launchd agent. Files and the Full Disk Access grant are left in place—remove those manually if you want a full teardown:

1. Delete the bridge folder: `rm -rf ~/imessage-bridge`
2. Remove FDA grant: System Settings → Privacy & Security → Full Disk Access → remove `cowork-imessage-helper`
3. Remove Automation grant: System Settings → Privacy & Security → Automation → remove `cowork-imessage-helper`

---

## Differences from Claude Cowork Setup

- **No `.plugin` file.** Grok Bot uses the raw skill Markdown directly; there's no Cowork-style plugin packaging.
- **No automatic asset copying.** You manually copy the install scripts to your bridge folder (Steps 2–3 above).
- **Bridge folder discovery is manual.** You tell Grok Bot where the bridge folder is; it doesn't auto-select a workspace like Cowork does.

The **helper itself is identical**—same C wrapper, same Python worker, same protocol. If you've used this with Cowork before, the only difference is how you enable the skill and where the bridge folder lives.

---

## Known Limitations

- **macOS-only.** The helper relies on Apple-internal SQLite schemas (`chat.db`, `AddressBook-v22.abcddb`) that have no stability guarantee. Future macOS releases could break it.
- **Text-only.** No attachments, images, stickers, audio, Tapback reactions, or message effects.
- **No message editing or deletion.** Once sent, a message is immutable.
- **No group-chat creation.** Can send *to* an existing group, but not stand one up.
- **Local `chat.db` only.** If a thread hasn't synced to this Mac, it won't appear in search/review.

---

## References

- **Full protocol documentation:** `docs/PROTOCOL.md`
- **Skill file:** `hosts/grok-bot/SKILL.md`
- **Security details:** `SECURITY.md` (in the repo root)
- **Source & releases:** [github.com/jeffhuber/claudecowork-imessage-skill](https://github.com/jeffhuber/claudecowork-imessage-skill)

---

## License

MIT. See `LICENSE` in the repo root.
