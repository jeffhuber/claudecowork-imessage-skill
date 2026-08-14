#!/bin/bash
# Copy the complete, versioned helper payload into a Cowork-selected bridge.

set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINATION="${1:-}"

if [[ -z "$DESTINATION" ]]; then
    echo "Usage: $0 <bridge-folder>" >&2
    exit 2
fi

while [[ "$DESTINATION" != "/" && "$DESTINATION" == */ ]]; do
    DESTINATION="${DESTINATION%/}"
done
if [[ -L "$DESTINATION" || (-e "$DESTINATION" && ! -d "$DESTINATION") ]]; then
    echo "Error: bridge must be a regular directory, not a symlink: $DESTINATION" >&2
    exit 1
fi
mkdir -p "$DESTINATION"
DESTINATION="$(cd "$DESTINATION" && pwd -P)"
for directory in bin tools contacts; do
    path="$DESTINATION/$directory"
    if [[ -L "$path" || (-e "$path" && ! -d "$path") ]]; then
        echo "Error: bridge subdirectory must be a regular directory: $path" >&2
        exit 1
    fi
    mkdir -p "$path"
done

copy_asset() {
    local source="$1"
    local destination="$2"
    local parent="${destination%/*}"
    local temporary

    if [[ -L "$destination" || (-e "$destination" && ! -f "$destination") ]]; then
        echo "Error: refusing unsafe bootstrap destination: $destination" >&2
        return 1
    fi
    temporary="$(mktemp "$parent/.imessage-bootstrap.XXXXXX")"
    if ! cp "$source" "$temporary"; then
        rm -f "$temporary"
        return 1
    fi
    if ! mv -f "$temporary" "$destination"; then
        rm -f "$temporary"
        return 1
    fi
}

for file in \
    install.sh \
    install-hardened.sh \
    uninstall.sh \
    uninstall-hardened.sh \
    com.jeffhuber.claudecowork-imessage.plist.template; do
    copy_asset "$SOURCE_ROOT/$file" "$DESTINATION/$file"
done
for file in \
    imessage_helper.c \
    confirm_imessage_send.m \
    helper.py \
    send_gate.py; do
    copy_asset "$SOURCE_ROOT/bin/$file" "$DESTINATION/bin/$file"
done
for file in migrate_legacy_launchagent.py doctor.py configure_allowlist.py \
    select_python.sh; do
    copy_asset "$SOURCE_ROOT/tools/$file" "$DESTINATION/tools/$file"
done
for file in allowed_chats.txt.template blocked_chats.txt.template; do
    copy_asset "$SOURCE_ROOT/contacts/$file" "$DESTINATION/contacts/$file"
done
chmod 700 "$DESTINATION/install.sh" "$DESTINATION/install-hardened.sh" \
    "$DESTINATION/uninstall.sh" "$DESTINATION/uninstall-hardened.sh"
chmod 700 "$DESTINATION/tools/"*.py
chmod 700 "$DESTINATION/tools/select_python.sh"

echo "Copied the complete Claude Cowork iMessage helper to $DESTINATION"
echo "Next: cd \"$DESTINATION\" && ./install.sh"
