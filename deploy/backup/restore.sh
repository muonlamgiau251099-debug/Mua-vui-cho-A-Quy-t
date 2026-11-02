#!/bin/sh
# Khôi phục một bản sao lưu vào database đích (mặc định: tlmn_restore — KHÔNG ghi đè DB đang chạy).
#   docker compose -f deploy/docker-compose.yml exec backup sh /scripts/restore.sh /backups/tlmn-....dump [db_đích]
# Kiểm tra xong mới đổi app sang DB đã khôi phục (xem docs/runbook.md §Khôi phục).
set -eu
dump="${1:?Thiếu đường dẫn file .dump}"
target="${2:-tlmn_restore}"
psql --dbname=postgres --command="DROP DATABASE IF EXISTS \"$target\"" --command="CREATE DATABASE \"$target\""
pg_restore --no-owner --dbname="$target" --exit-on-error "$dump"
psql --dbname="$target" --tuples-only --command="
  SELECT 'games=' || count(*) FROM games
  UNION ALL SELECT 'game_events=' || count(*) FROM game_events
  UNION ALL SELECT 'score_transfers=' || count(*) FROM score_transfers
  UNION ALL SELECT 'rule_versions=' || count(*) FROM global_rule_versions"
echo "Đã khôi phục vào database: $target"
