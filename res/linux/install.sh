#!/bin/sh
# Installs FastGH for this user: the program in ~/.local/share/FastGH (where its
# updater replaces it), a FastGH command in ~/.local/bin, and an entry in the
# applications menu. Run it from the unpacked FastGH folder:
#   ./install.sh              install or update
#   ./install.sh --uninstall  remove it (settings in ~/.config/FastGH are kept)
set -e

here=$(cd "$(dirname "$0")" && pwd)
data=${XDG_DATA_HOME:-$HOME/.local/share}
dest="$data/FastGH"
bin="$HOME/.local/bin"
apps="$data/applications"
icons="$data/icons/hicolor/256x256/apps"

if [ "$1" = "--uninstall" ]; then
    rm -f "$bin/FastGH" "$apps/FastGH.desktop" "$icons/FastGH.png"
    rm -rf "$dest"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true
    echo "FastGH has been removed. Its settings are still in ${XDG_CONFIG_HOME:-$HOME/.config}/FastGH."
    exit 0
fi

mkdir -p "$dest" "$bin" "$apps" "$icons"
if [ "$here" != "$dest" ]; then
    for f in FastGH FastGH.png FastGH.desktop install.sh; do
        # Through a temporary name: a running FastGH can't be written over.
        cp "$here/$f" "$dest/$f.new" && mv -f "$dest/$f.new" "$dest/$f"
    done
fi
chmod +x "$dest/FastGH" "$dest/install.sh"
ln -sf "$dest/FastGH" "$bin/FastGH"
cp "$here/FastGH.png" "$icons/FastGH.png"
sed "s|^Exec=.*|Exec=\"$dest/FastGH\"|" "$here/FastGH.desktop" > "$apps/FastGH.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$data/icons/hicolor" || true

echo "FastGH is installed in $dest."
echo "Start it from your applications menu, or run FastGH (from $bin)."
