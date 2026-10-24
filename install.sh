#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
BACKUP_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles-backup/$(date +%Y%m%d-%H%M%S)"

if [[ "$(id -u)" -eq 0 ]]; then
    echo "Run this script as a regular user, not as root." >&2
    exit 1
fi

if [[ "${1:-}" != "--yes" ]]; then
    echo "Files in $CONFIG_DIR and $HOME will be replaced with symlinks to $REPO_DIR."
    echo "Existing files will be backed up to $BACKUP_DIR"
    read -r -p "Continue? [y/N] " answer
    [[ "$answer" == [yY] ]] || exit 1
fi

link_item() {
    local source="$1"
    local target="$2"
    local rel="${target#"$HOME"/}"

    if [[ -L "$target" ]]; then
        rm -f "$target"
    elif [[ -e "$target" ]]; then
        mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
        mv "$target" "$BACKUP_DIR/$rel"
        printf 'backup  %s\n' "$rel"
    fi

    mkdir -p "$(dirname "$target")"
    ln -s "$source" "$target"
    printf 'link    %s -> %s\n' "$rel" "$source"
}

for source in "$REPO_DIR"/config/*; do
    link_item "$source" "$CONFIG_DIR/$(basename "$source")"
done

for source in "$REPO_DIR"/home/.[!.]* "$REPO_DIR"/home/*; do
    [[ -e "$source" ]] || continue
    link_item "$source" "$HOME/$(basename "$source")"
done

echo
echo "Done. Backup: $BACKUP_DIR"
