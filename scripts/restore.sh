#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh.  DESTROYS the current data.
#
#   scripts/restore.sh backups/20261124T200000Z
#
# Stops the app services, recreates the database from the dump, restores media,
# then starts everything again (migrations run on start).
set -euo pipefail

SRC="${1:?usage: scripts/restore.sh <backup-dir>}"
[[ -f "$SRC/db.dump" ]] || { echo "No db.dump in $SRC" >&2; exit 1; }
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
[[ "${BACKUP_DEV:-0}" == 1 ]] && COMPOSE=(docker compose)

if [[ "${CONFIRM:-}" != "yes" ]]; then
  read -r -p "This replaces ALL current data with $SRC. Type 'yes' to continue: " answer
  [[ "$answer" == "yes" ]] || { echo "Aborted."; exit 1; }
fi

"${COMPOSE[@]}" stop api bot worker frontend nginx
"${COMPOSE[@]}" exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
"${COMPOSE[@]}" exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' < "$SRC/db.dump"

if [[ -f "$SRC/media.tar.gz" ]]; then
  "${COMPOSE[@]}" run --rm --no-deps -T --entrypoint sh api -c 'find /app/media -mindepth 1 -delete; tar -C /app/media -xzf -' < "$SRC/media.tar.gz"
fi

"${COMPOSE[@]}" up -d
echo "Restored from $SRC"
