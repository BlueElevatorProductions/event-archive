#!/bin/bash
# Build ~/Applications/Event Archive.app: a tiny launcher that makes sure the
# local server is running and opens the page. Re-run after changing the icon.
#   bash launcher/make_app.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"          # wherever this project folder lives
APP="$HOME/Applications/Event Archive.app"
TMP="$(mktemp -d)"

[ -f "$HERE/icon-1024.png" ] || uv run "$HERE/make_icon.py"
SET="$TMP/EventArchive.iconset"; mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$HERE/icon-1024.png" --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$HERE/icon-1024.png" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
iconutil -c icns "$SET" -o "$APP/Contents/Resources/EventArchive.icns"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Event Archive</string>
  <key>CFBundleDisplayName</key><string>Event Archive</string>
  <key>CFBundleIdentifier</key><string>local.eventarchive.launcher</string>
  <key>CFBundleExecutable</key><string>EventArchive</string>
  <key>CFBundleIconFile</key><string>EventArchive</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/EventArchive" <<'LAUNCH'
#!/bin/bash
# Event Archive.app launcher: start the local server if it isn't running, then open the page.
# Installed by launcher/make_app.sh; re-run that if you move the project folder.
REPO="__REPO__"
LOG="$HOME/Library/Logs/EventArchive.log"
URL="http://localhost:5177"
up() { /usr/bin/curl -s -o /dev/null --max-time 1 "$URL/api/people"; }
if ! up; then
    UV="$(PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH" command -v uv)"
    if [ -n "$UV" ]; then
        cd "$REPO" && nohup "$UV" run app/server.py >>"$LOG" 2>&1 &
        for _ in $(seq 1 60); do up && break; sleep 0.5; done
    fi
fi
if ! up; then
    osascript -e 'display notification "The server did not start. See ~/Library/Logs/EventArchive.log" with title "Event Archive"' >/dev/null 2>&1
    exit 1
fi
open "$URL"
LAUNCH
/usr/bin/python3 - "$APP/Contents/MacOS/EventArchive" "$REPO" <<'PY'
import sys
p, repo = sys.argv[1], sys.argv[2]
text = open(p).read().replace("__REPO__", repo.replace('"', '\\"'))
open(p, "w").write(text)
PY
chmod +x "$APP/Contents/MacOS/EventArchive"
codesign --force --sign - "$APP" >/dev/null 2>&1 || true
touch "$APP"
rm -rf "$TMP"
echo "built $APP"
