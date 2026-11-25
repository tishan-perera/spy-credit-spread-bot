#!/bin/sh
# One pass of the background watcher (run every 15 minutes by ops/watch-service.sh):
#  1. health check: a Mac notification for every new missed or failed logger run, stale history
#     or a calendar that is running out (each problem is notified once);
#  2. backup: copy the logged quotes and history to iCloud Drive. Files are only added or updated,
#     never deleted from the backup. Set SPYBOT_BACKUP_DIR to back up somewhere else.
set -u
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP="${SPYBOT_BACKUP_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/SPY-bot-backup}"
cd "$PROJECT" || exit 1
echo "--- $(date '+%Y-%m-%d %H:%M:%S')"
.venv/bin/python -m spybot health --notify
mkdir -p "$BACKUP" && for d in raw snapshots history cboe; do
    [ -d "data/$d" ] && rsync -a "data/$d" "$BACKUP/"
done && echo "backup ok: $BACKUP"
