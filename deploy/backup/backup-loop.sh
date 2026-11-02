#!/bin/sh
# Sao lưu PostgreSQL định kỳ (mặc định mỗi ngày), giữ BACKUP_KEEP_DAYS ngày (docs/gd2/06 §1).
set -eu
while true; do
  sh /scripts/backup-once.sh
  sleep "${BACKUP_INTERVAL_SECONDS:-86400}"
done
