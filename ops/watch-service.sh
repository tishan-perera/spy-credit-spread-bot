#!/bin/sh
# Run the background watcher (ops/watch.sh) every 15 minutes on this Mac (a user LaunchAgent):
# Mac notifications for missed or failed logger runs, and a backup of the logged data to iCloud Drive.
#
#   sh ops/watch-service.sh install     run now, every 15 minutes, and at every login
#   sh ops/watch-service.sh uninstall   stop it and remove the service
#   sh ops/watch-service.sh status      is it loaded? (last exit code 0 = last pass worked)
#
# Log: ~/Library/Logs/spybot-watch.log
set -eu

LABEL="local.spybot.watch"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/spybot-watch.log"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
install)
    [ -x "$PROJECT/.venv/bin/python" ] || { echo "No $PROJECT/.venv/bin/python; set up the project first."; exit 1; }
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string><string>$PROJECT/ops/watch.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>900</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "Installed. Runs every 15 minutes; log: $LOG"
    ;;
uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed."
    ;;
status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
        launchctl print "$DOMAIN/$LABEL" | grep -E "^\s*(state|pid|last exit code) ="
    else
        echo "Not installed."
    fi
    ;;
*)
    echo "usage: sh ops/watch-service.sh install|uninstall|status"; exit 2
    ;;
esac
