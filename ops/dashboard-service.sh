#!/bin/sh
# Run the read-only dashboard as a background service on this Mac (a user LaunchAgent),
# so it keeps running when Claude chats go idle or the Claude app updates itself.
#
#   sh ops/dashboard-service.sh install     start now, at every login, and restart if it stops
#   sh ops/dashboard-service.sh uninstall   stop it and remove the service
#   sh ops/dashboard-service.sh status      is it running?
#
# The page stays at http://127.0.0.1:8790 (this computer only). Log: ~/Library/Logs/spybot-dashboard.log
set -eu

LABEL="local.spybot.dashboard"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/spybot-dashboard.log"
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
    <string>$PROJECT/.venv/bin/python</string>
    <string>-m</string><string>spybot</string><string>dashboard</string><string>8790</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "Installed. Dashboard: http://127.0.0.1:8790"
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
    echo "usage: sh ops/dashboard-service.sh install|uninstall|status"; exit 2
    ;;
esac
