#!/usr/bin/env bash
# A cron ezt futtatja: rendelések a Google Sheetbe, fotók a Google Drive-ba.
# Használat: ./sync_all.sh prod   (a .env.prod beállításaival)
#            ./sync_all.sh dev    (a .env.dev beállításaival)
# Beállítás: README.md.
set -uo pipefail
cd "$(dirname "$0")"

ENV_NAME="${1:-}"
case "$ENV_NAME" in
  dev|prod) ;;
  *) echo "Használat: $0 dev|prod" >&2; exit 2 ;;
esac
ENV_FILE=".env.$ENV_NAME"
[[ -f "$ENV_FILE" ]] || { echo "Hiányzik: $ENV_FILE" >&2; exit 1; }
. "./$ENV_FILE"

echo "── $ENV_NAME $(date '+%Y-%m-%d %H:%M') ──"
.venv/bin/python sync_orders.py

# copy: csak új és megváltozott fájlokat másol, a Drive-ból soha nem töröl.
# Az AWS kulcsot az rclone a fenti .env fájlból veszi (env_auth), így a
# két környezet a saját kulcsával a saját bucketjéből olvas.
rclone copy "aws:${ORDER_PHOTOS_BUCKET}/orders" "gdrive:${DRIVE_FOLDER}" \
  --s3-no-check-bucket --log-level NOTICE
