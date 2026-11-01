#!/usr/bin/env bash
# Builds the "builder" AppImage: the launcher, build scripts, patches and the generic recompiler config.
# It contains NO game data and NO recompiled game code. On first run it builds the runtime from the user's own ISO.
#
# Usage: tools/appimage/build_appimage.sh [version] [out_dir]
#   APPDIR_ONLY=1   only assemble the AppDir (printed at the end) and skip appimagetool
#   APPIMAGETOOL=<path>   use this appimagetool instead of downloading the pinned release
set -euo pipefail
cd "$(dirname "$0")/../.."
VERSION="${1:-$(cat VERSION)}"
OUT="${2:-dist}"
APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
mkdir -p "$OUT"
APPDIR="$(mktemp -d)/GodOfWarRecomp.AppDir"
APP="$APPDIR/usr/share/gow-one-recomp"
mkdir -p "$APP"

# Only what the setup and the launcher need. Never game files, logs or build output.
cp -r tools scripts config patches src LICENSE VERSION "$APP/"
rm -rf "$APP/patches/anteriores" "$APP/tools/render" "$APP/tools/estado"
find "$APP" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "$VERSION" > "$APP/VERSION"

cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec python3 "$HERE/usr/share/gow-one-recomp/tools/linux/gow_app.py" "$@"
RUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/gow-one-recomp.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=God of War (recomp)
Comment=Static recompilation of God of War (PS2), built from your own ISO
Exec=AppRun
Icon=gow-one-recomp
Categories=Game;
Terminal=false
DESKTOP

# 256x256 solid-colour icon (no image tools needed in CI)
python3 - "$APPDIR/gow-one-recomp.png" <<'PY'
import struct, sys, zlib
w = h = 256
rows = b"".join(b"\x00" + bytes([150, 20, 20]) * w for _ in range(h))
def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
open(sys.argv[1], "wb").write(png)
PY
cp "$APPDIR/gow-one-recomp.png" "$APPDIR/.DirIcon"

if [ -n "${APPDIR_ONLY:-}" ]; then
  echo "AppDir assembled at $APPDIR"
  exit 0
fi

TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
  TOOL="${TMPDIR:-/tmp}/appimagetool-$APPIMAGETOOL_VERSION-x86_64.AppImage"
  if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VERSION/appimagetool-x86_64.AppImage"
    echo "$APPIMAGETOOL_SHA256  $TOOL" | sha256sum -c -
    chmod +x "$TOOL"
  fi
fi
FILE="$OUT/gow-one-recomp-$VERSION-x86_64.AppImage"
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$FILE"
(cd "$OUT" && sha256sum "$(basename "$FILE")" > "$(basename "$FILE").sha256")
echo "Built $FILE"
