#!/usr/bin/env bash
# A cron ezt futtatja: rendelések a Google Sheetbe, fotók a Google Drive-ba.
# Beállítás: README.md.
set -uo pipefail
cd "$(dirname "$0")"
. ./.env

echo "── $(date '+%Y-%m-%d %H:%M') ──"
.venv/bin/python sync_orders.py

# copy: csak új és megváltozott fájlokat másol, a Drive-ból soha nem töröl.
rclone copy "aws:${ORDER_PHOTOS_BUCKET}/orders" "gdrive:${DRIVE_FOLDER}" \
  --s3-no-check-bucket --log-level NOTICE
