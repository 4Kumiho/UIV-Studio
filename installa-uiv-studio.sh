#!/usr/bin/env sh
# UIV Studio installer for Linux: downloads the latest "UIV Studio" executable
# next to this script and starts it. Run it again to update.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
URL="https://github.com/4Kumiho/uiv-studio/releases/latest/download/UIV-Studio-linux"
DEST="$DIR/UIV Studio"

echo "UIV Studio: download dell'ultima versione / downloading the latest version..."
if command -v curl >/dev/null 2>&1; then
  curl -fL --progress-bar -o "$DEST.download" "$URL"
elif command -v wget >/dev/null 2>&1; then
  wget -q --show-progress -O "$DEST.download" "$URL"
else
  echo "Serve curl o wget / curl or wget is required" >&2
  exit 1
fi
mv -f "$DEST.download" "$DEST"
chmod +x "$DEST"
echo "Installato / Installed: $DEST"
nohup "$DEST" >/dev/null 2>&1 &
