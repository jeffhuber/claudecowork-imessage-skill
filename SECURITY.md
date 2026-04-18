# Security

This document describes what `imessage-review` does with your Mac's
permissions, the trust boundaries it relies on, and what to do if you
find a vulnerability.

It is written to be specific about limitations rather than reassuring.
If something below sounds too permissive for your threat model, don't
install the plugin.

## What this plugin does

`imessage-review` is a Claude Cowork plugin that:

- Reads your local Messages database (`~/Library/Messages/chat.db`) so
  Claude can search, summarize, and surface messages that need a reply.
- Optionally sends iMessages on your behalf, gated behind an in-Cowork
  preview-and-confirm step.

Both paths go through a single on-device helper process: a Python
script (`helper.py`) launched by an ad-hoc-signed C wrapper via a
user-scoped `launchd` LaunchAgent. The C wrapper exists solely to give
the helper a stable `CDHash`, which is what macOS TCC uses to identify
the process holding Full Disk Access.

## Permissions required, and what each one actually grants

### Full Disk Access (FDA)

Required to read `chat.db`. macOS does not offer a narrower grant —
FDA is the coarsest of the TCC permissions and is functionally "read
anything this user can read."

Concretely, FDA on this helper gives the helper process the ability
to read:

- The entire Messages database, including attachments.
- Other apps' protected storage (Mail, Safari history, calendars,
  `Library/Application Support/*`).
- Any user file that isn't itself TCC-gated.

The plugin *code* only reads `chat.db`. But a bug or compromise in
the helper becomes a full-user-file-read primitive, not just a
Messages leak. Treat that as the blast radius.

### Automation → Messages (v0.3.0+)

Required to send. The first send triggers a one-time macOS prompt:
"cowork-imessage-helper wants to control Messages." The grant lives
under System Settings → Privacy & Security → Automation →
cowork-imessage-helper → Messages.

Concretely, this grants the helper the ability to:

- Send iMessages or SMS to any recipient, from any of your
  iMessage-enabled addresses.
- Query Messages.app AppleScript state (services, buddies, chats).

It does NOT grant access to attachments, effects, edit/delete, or
group-chat creation — those aren't in the AppleScript surface.

## Trust boundaries

The helper communicates with Claude via a **bridge folder** — a
mode-700 directory under the user's home directory (`~/cowork-imessage/`)
where the client writes request files and the helper writes response
files. `launchd`'s `WatchPaths` triggers the helper on change.

This is the primary trust boundary you need to understand.

**What the bridge folder protects against:**

- Other user accounts on the same machine. The folder is `700`; only
  the owning UID can read or write.
- Sandboxed apps that don't have access to `$HOME`.

**What the bridge folder does NOT protect against:**

- Any unsandboxed process running as your user. If you run a malicious
  `npm install`, `pip install`, `brew install`, or anything else that
  executes as your UID, that process can:
  - Write a read request into the bridge folder and receive message
    contents in response.
  - Write a `send` request and the helper will send it.

This is the central limitation of the current (v0.3.x) design. A
signed-request (HMAC) model is planned but not yet in place. If your
threat model includes malicious supply-chain packages running as your
user, do not install this plugin in its current form.

## Confirmation gate (sending)

Sending is confirmation-gated via a preview/confirm protocol:

1. The client asks the helper for a `send_preview` — the helper does
   NOT send; it echoes back the normalized payload.
2. Claude shows the preview to you; you approve.
3. The client asks the helper to `send`.

In v0.3.x the gate is enforced **client-side** (in the Claude skill),
not helper-side. A process that writes directly to the bridge folder
can skip step 2 and issue a `send` immediately. A helper-side
nonce-based gate is planned.

## Blocklist

`contacts/blocked_chats.txt` is checked by the helper before any read
or send involving a listed identifier. The list is editable by the
user and is honored for both inbound (search/review) and outbound
(send) as of v0.3.0.

The blocklist is best-effort. It is not a privacy boundary — anyone
who can edit the file can also remove entries, and the helper trusts
the list verbatim. Use it to prevent accidental exposure, not as a
security control.

## What leaves the machine

The helper itself does not make any outbound network connections. All
message content read from `chat.db` or sent via AppleScript is
processed on-device by the helper.

When Claude Cowork uses the plugin, message content that Claude reads
passes through Claude's normal pipeline, which means it reaches
Anthropic's servers as part of the conversation, subject to
Anthropic's standard data-handling terms. If you don't want a specific
conversation touched, add the identifier to the blocklist or don't
invoke the skill on that range.

The plugin does **not**:

- Send telemetry.
- Phone home.
- Auto-update.
- Log message content to disk outside of the short-lived `chat.db`
  copy used for reads (see below).

## The chat.db copy

SQLite locks `chat.db` while Messages.app has it open, so the helper
copies it to a per-request tempfile under the user's cache directory,
reads the copy, and deletes it at the end of the request. The copy is
mode-600 and is cleaned up on normal exit; an abnormal exit (OOM,
SIGKILL) can leave a stale copy behind.

`send` actions do NOT copy `chat.db` — a `needs_db` flag on each
request handler short-circuits the copy for write-only operations.

## Third-party privacy

Messages are two-sided. Every message this plugin reads was sent to
or from someone else, and they never consented to have their words
processed by an LLM. If you use this plugin, you are making that
choice on their behalf.

This is not a flaw in the code; it's an intrinsic property of giving
an assistant access to your messages. It's mentioned here because it's
a legitimate concern that the README should not bury.

## Durability

This plugin depends on two Apple surfaces that are not contractually
stable:

- Direct read access to `~/Library/Messages/chat.db`. Apple has
  tightened TCC over several macOS releases and could close this
  further.
- AppleScript control of Messages.app. AppleScript support across
  Apple's own apps has been trending down for years.

Either could be deprecated in a future macOS release. If that
happens, this plugin will need to be rewritten or will stop working.

## Auditing this plugin

You can verify what's actually on your disk:

- The `.plugin` bundle is a flat zip. Unzip it and read
  `skills/imessage-review/helper.py` — it's pure Python and the only
  thing that runs with FDA + Automation-over-Messages.
- The C wrapper source is in the bundle. It does approximately
  nothing — it exists to stabilize the CDHash. You can rebuild it
  yourself; the README documents the one-line `clang` command.
- Verify the released `.plugin` matches the source on GitHub. Each
  GitHub release attaches the bundle; the file is small enough to
  diff against a local clone.
- After install, verify the plugin's LaunchAgent plist under
  `~/Library/LaunchAgents/` points only at the wrapper in the bridge
  folder and carries no other arguments.

## Revoking

To fully remove the plugin's access:

1. In Cowork, remove the plugin.
2. `launchctl unload ~/Library/LaunchAgents/<plugin-plist>.plist`
3. `rm ~/Library/LaunchAgents/<plugin-plist>.plist`
4. `rm -rf ~/cowork-imessage` (bridge folder; includes helper and
   any pending request/response files).
5. System Settings → Privacy & Security → Full Disk Access → remove
   `cowork-imessage-helper`.
6. System Settings → Privacy & Security → Automation →
   cowork-imessage-helper → turn Messages off (or remove the entry
   entirely).

## Reporting a vulnerability

If you find a security issue, please do NOT open a public GitHub
issue. Email <jhuber+coworkimessageplugin@gmail.com> with details and, if possible, a
minimal reproduction. I will acknowledge within a few days and
coordinate disclosure.
