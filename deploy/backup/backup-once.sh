#!/bin/sh
# Một lần sao lưu: pg_dump định dạng custom → /backups/tlmn-YYYYmmdd-HHMMSS.dump, rồi xóa bản cũ.
# Chạy tay: docker compose -f deploy/docker-compose.yml exec backup sh /scripts/backup-once.sh
set -eu
file="/backups/tlmn-$(date -u +%Y%m%d-%H%M%S).dump"
pg_dump --format=custom --no-owner --file="$file.partial"
mv "$file.partial" "$file"   # chỉ đổi tên khi dump xong: không bao giờ để lại file dở dang
echo "Đã sao lưu: $file ($(du -h "$file" | cut -f1))"
find /backups -name 'tlmn-*.dump' -mtime "+${BACKUP_KEEP_DAYS:-14}" -print -delete
