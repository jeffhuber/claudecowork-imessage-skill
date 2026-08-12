#!/bin/bash
# Copy the complete, versioned helper payload into a Cowork-selected bridge.

set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINATION="${1:-}"

if [[ -z "$DESTINATION" ]]; then
    echo "Usage: $0 <bridge-folder>" >&2
    exit 2
fi

mkdir -p "$DESTINATION/bin" "$DESTINATION/tools"
for file in \
    install.sh \
    uninstall.sh \
    com.jeffhuber.claudecowork-imessage.plist.template; do
    cp "$SOURCE_ROOT/$file" "$DESTINATION/$file"
done
for file in \
    cowork_imessage_helper.c \
    helper.py \
    send_gate.py; do
    cp "$SOURCE_ROOT/bin/$file" "$DESTINATION/bin/$file"
done
cp "$SOURCE_ROOT/tools/migrate_legacy_launchagent.py" "$DESTINATION/tools/"
chmod 700 "$DESTINATION/install.sh" "$DESTINATION/uninstall.sh"
chmod 700 "$DESTINATION/tools/migrate_legacy_launchagent.py"

echo "Copied the complete Claude Cowork iMessage helper to $DESTINATION"
echo "Next: cd \"$DESTINATION\" && ./install.sh"
