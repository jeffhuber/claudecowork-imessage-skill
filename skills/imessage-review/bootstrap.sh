#!/bin/bash
# Copy the complete, versioned helper payload into a Cowork-selected bridge.

set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINATION="${1:-}"

if [[ -z "$DESTINATION" ]]; then
    echo "Usage: $0 <bridge-folder>" >&2
    exit 2
fi

mkdir -p "$DESTINATION/bin" "$DESTINATION/tools" "$DESTINATION/contacts"
for file in \
    install.sh \
    install-hardened.sh \
    uninstall.sh \
    uninstall-hardened.sh \
    com.jeffhuber.claudecowork-imessage.plist.template; do
    cp "$SOURCE_ROOT/$file" "$DESTINATION/$file"
done
for file in \
    imessage_helper.c \
    confirm_imessage_send.m \
    helper.py \
    send_gate.py; do
    cp "$SOURCE_ROOT/bin/$file" "$DESTINATION/bin/$file"
done
cp "$SOURCE_ROOT/tools/migrate_legacy_launchagent.py" "$DESTINATION/tools/"
cp "$SOURCE_ROOT/tools/doctor.py" "$DESTINATION/tools/"
cp "$SOURCE_ROOT/tools/configure_allowlist.py" "$DESTINATION/tools/"
cp "$SOURCE_ROOT/contacts/allowed_chats.txt.template" "$DESTINATION/contacts/"
cp "$SOURCE_ROOT/contacts/blocked_chats.txt.template" "$DESTINATION/contacts/"
chmod 700 "$DESTINATION/install.sh" "$DESTINATION/install-hardened.sh" \
    "$DESTINATION/uninstall.sh" "$DESTINATION/uninstall-hardened.sh"
chmod 700 "$DESTINATION/tools/"*.py

echo "Copied the complete Claude Cowork iMessage helper to $DESTINATION"
echo "Next: cd \"$DESTINATION\" && ./install.sh"
