#!/bin/bash
# Günlük yedek. Cron örneği (her gece 03:15):
#   15 3 * * * cd /opt/sparetwin/deploy && ./backup.sh >> backups/backup.log 2>&1
# Yedekleri ayrıca sunucu dışına (başka bölgedeki depolama) kopyalamayı unutma.
set -euo pipefail
cd "$(dirname "$0")"
source .env
STAMP=$(date +%Y%m%d-%H%M)
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U postgres -d "$APP_DB_NAME" -Fc -f "/backups/sparetwin-$STAMP.dump"
docker run --rm -v deploy_media:/media:ro -v "$PWD/backups:/out" alpine:3.21 \
  tar czf "/out/media-$STAMP.tgz" -C /media .
# 14 günden eski yedekleri sil
find backups -name 'sparetwin-*.dump' -mtime +14 -delete
find backups -name 'media-*.tgz' -mtime +14 -delete
echo "Yedek tamam: $STAMP"
