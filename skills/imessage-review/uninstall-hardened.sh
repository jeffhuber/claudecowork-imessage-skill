#!/bin/bash
# Remove the hardened helper while preserving the user-owned runtime bridge.

set -euo pipefail
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
export PATH

if [[ "$EUID" -eq 0 ]]; then
    echo "Error: run as your normal user; this script invokes sudo narrowly." >&2
    exit 1
fi

LABEL="com.jeffhuber.claudecowork-imessage"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
PRODUCT_ROOT="/Library/Application Support/ClaudeCoworkIMessage"
USER_ROOT="$PRODUCT_ROOT/users/$UID"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BRIDGE_ROOT="${CLAUDE_COWORK_IMESSAGE_BRIDGE:-$SCRIPT_ROOT}"

if launchctl print "gui/$UID/$LABEL" >/dev/null 2>&1; then
    launchctl bootout "gui/$UID/$LABEL"
    echo "  launchd agent unloaded"
fi
if [[ -f "$PLIST_DEST" ]]; then
    rm -f "$PLIST_DEST"
    echo "  removed $PLIST_DEST"
fi
if [[ -d "$USER_ROOT" ]]; then
    sudo /bin/rm -rf "$USER_ROOT"
    echo "  removed root-owned helper $USER_ROOT"
    if sudo /bin/rmdir "$PRODUCT_ROOT/users" 2>/dev/null; then
        if ! sudo /bin/rmdir "$PRODUCT_ROOT" 2>/dev/null; then
            echo "  retained non-empty $PRODUCT_ROOT"
        fi
    fi
fi

cat <<EOF

Hardened helper uninstalled. Runtime data remains at:
  $BRIDGE_ROOT

Delete that directory only after reviewing any responses/logs you need.
Revoke claude-cowork-imessage-helper under Full Disk Access and Automation in
System Settings -> Privacy & Security.
EOF
