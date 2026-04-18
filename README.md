# imessage-review

Read, search, and analyze your iMessages on macOS from inside Claude Cowork.

## What's in the box

- **Skill** `imessage-review` — teaches Claude the full protocol for reading
  the Messages database via an on-device helper. Triggers on natural
  language like "show me iMessages from X", "triage my unread messages",
  "average reply time to Y", etc.
- **Command** `/imessages [days]` — one-shot triage of the last N days
  (default 2). Categorizes threads into needs-reply / low-priority / skipped.
- **Bundled helper** — source for a tiny hardened C wrapper that holds the
  Full Disk Access grant, plus the Python worker that reads `chat.db`,
  resolves contacts, redacts sensitive content, and writes JSON responses.

## How it works

The Cowork agent runs in a Linux sandbox that can't see `~/Library/Messages`.
This plugin installs a `launchd` agent on your Mac that watches for JSON
request files in a *bridge folder* (any folder you select as your Cowork
workspace). When Claude writes a request file, launchd fires the helper,
which reads the Messages database, processes the request, and writes a JSON
response back into the same folder — where Claude can then read it.

```
  Cowork (Linux sandbox)                 Your Mac
  ----------------------                 --------
  writes request.json  -->  launchd  -->  helper reads chat.db
                                          writes response.json
  reads response.json  <-----------------/
```

Sending iMessages uses Claude's Computer Use to drive Messages.app directly
(no helper involvement).

## Install

### The fast path — from a release

1. Go to the [Releases page](../../releases/latest) and download
   `imessage-review.plugin`.
2. In Cowork, drag the `.plugin` file into the app (or use "Install
   plugin" and point it at the file).
3. Pick a **bridge folder** — any directory on your Mac that Cowork can
   write to. Example: `~/Documents/imessage-bridge`. Select it as your
   Cowork workspace.
4. Ask Claude "set up the iMessage helper for this folder." Claude will
   copy the installer assets into the folder and run `install.sh` for
   you. (Or do it manually — `cd <bridge folder> && ./install.sh`.)
5. `install.sh` will print the exact path of the compiled wrapper binary
   and tell you to grant Full Disk Access. Open
   System Settings → Privacy & Security → Full Disk Access → **+** →
   paste the path → toggle on.
6. Verify: ask Claude to "triage my iMessages from the last day" or run
   `/imessage-review:imessages 1`.

### The source path — build it yourself

```
git clone https://github.com/jeffhuber/claudecowork-imessage-skill.git
cd claudecowork-imessage-skill
zip -r imessage-review.plugin . -x "*.DS_Store" "__pycache__/*" "*/__pycache__/*" ".git/*"
```

Then drag `imessage-review.plugin` into Cowork and continue with steps 3–6
above.

## Requirements

- macOS (the helper is Apple-specific — SQLite + launchd + Contacts.app).
- Xcode Command Line Tools (`xcode-select --install`) — for `clang` and
  `codesign` during install.
- Python 3 (uses `/usr/bin/python3` if available, otherwise `$PATH`).

## Privacy

### Automatic redaction

Before returning a response, the helper runs a regex-based redactor that
masks:

- 2FA / verification codes (`code`, `passcode`, `OTP`, `one-time` contexts)
- Credit-card-like digit runs (13–19 digits, with or without `-` / space
  separators)
- US SSN patterns (`NNN-NN-NNNN`)

### Thread-level blocklist

You can block entire threads from ever entering Claude's context by adding
them to `<bridge folder>/contacts/blocked_chats.txt` (phone numbers,
emails, or group-chat IDs — one per line). Blocked threads are dropped
before the redactor even runs.

### Consent — the thing nobody else on the thread agreed to

When you use this plugin, you're piping both sides of your conversations —
including messages you received from other people — into a commercial LLM
(Claude). Those people didn't consent to that, and in many cases they'd
reasonably object if they knew. This is an unavoidable property of any
"read my messages" tool, but it's worth sitting with before you run this
every morning as a habit.

**Strongly consider preemptively blocklisting** any thread that contains
messages you would not want an LLM to read, including:

- Therapists, counselors, clergy, medical providers
- Attorneys and anyone else you have privileged communication with
- Financial advisors, accountants
- Family members during a dispute or sensitive life event
- Minors (your kids, your kids' friends, babysitters, etc.)
- Anyone who has explicitly told you "please keep this between us"
- Journalists or sources, if you're one of those people
- Anyone in a jurisdiction with two-party-consent recording laws where
  running their messages through a third party might be an issue

Adding a chat to `contacts/blocked_chats.txt` is a one-line operation and
is enforced *before* redaction — those messages never reach Claude at all.

## Known limitations

Being upfront about what this tool does and doesn't do. None of these are
reasons to avoid using it — they're reasons to use it with your eyes open.

### Redaction is regex-based and has documented gaps

The redactor catches the common 2FA / card / SSN cases but is not a DLP
product. Known bypasses (all have regression tests under
`tests/test_redaction.py::RedactionKnownBypasses`, marked
`@expectedFailure`):

- Dot-separated credit cards (`4111.1111.1111.1111`)
- PIN-labelled codes (`Your PIN is 4829` — "PIN" isn't in the keyword list)
- Slash-separated SSNs (`123/45/6789`)
- Bare verification codes with no keyword (`839201 to confirm it's you`)
- API keys (Stripe `sk_live_*`, GitHub tokens, OpenAI keys, etc.)
- Bank account / routing numbers (below the 13-digit card floor)
- Home addresses
- Dates of birth

If you close one of these gaps, flip the `@unittest.expectedFailure`
decorator off in the matching test and it becomes a regression guard.

**Implication:** assume sensitive content will occasionally slip through.
The thread-level blocklist is the reliable filter; the regex is a
second line of defense, not the first.

### Full Disk Access grant is tied to a specific binary hash

The grant is attached to the ad-hoc-signed helper's **CDHash**, not its
path. That means:

- Re-running the installer against a **bit-identical** source rebuilds the
  same CDHash and the grant carries over.
- Changing the C source, the Python, or even a compiler version *can*
  produce a different CDHash, at which point macOS will silently drop
  requests until you re-grant FDA to the new binary.
- macOS can also invalidate the grant on its own — major OS upgrades,
  Spotlight reindex weirdness, or TCC resets have all been reported.

**Symptom:** the helper stops responding, requests pile up unprocessed in
the bridge folder. **Fix:** re-open System Settings → Privacy & Security
→ Full Disk Access, remove the old entry, re-add the binary at the path
the installer prints.

### Privacy tradeoff: messages flow through a commercial LLM

This is not a local LLM pipeline. Every thread you surface flows through
Anthropic's API as part of the Claude context window and is subject to
Anthropic's data handling and retention policies, not yours. If that's not
acceptable for a specific conversation, blocklist it (see above).

### macOS-only, and leans on private-ish schemas

`chat.db` and `AddressBook-v22.abcddb` are Apple-internal SQLite schemas
with no stability guarantee. They've been stable for years, but a future
macOS release could rename a column and break the helper until someone
patches the queries. Same applies to the `attributedBody` typedstream
format that the decoder in `helper.py` reverse-engineers.

### The helper reads; the sender path is GUI automation

Reading is clean (launchd + SQLite). **Sending** is done by driving
Messages.app with Computer Use — typing into text fields, pressing return.
That path is inherently flakier than an API call and can fail in subtle
ways (wrong thread selected if Messages is mid-scroll, stuck at a
confirmation dialog, etc.). Review before hitting send.

## Uninstall

Run `./uninstall.sh` from the bridge folder. This removes the launchd
agent. Files and the Full Disk Access grant are left in place — remove
those manually if you want a full teardown.

## Development

```
python3 -m unittest discover -s tests -v
```

Tests cover the attributedBody decoder, the redaction regexes (plus the
documented known-bypass cases), and request-parameter validation. See
`tests/README.md` for details.

## License

MIT
