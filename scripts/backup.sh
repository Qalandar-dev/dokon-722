#!/usr/bin/env bash
# Back up the database and uploaded media of a running Docker Compose deployment.
#
#   scripts/backup.sh [backup-dir]        (default: ./backups)
#
# Produces <dir>/<timestamp>/db.dump (pg_dump custom format) and media.tar.gz.
# Run from the project root. Schedule it (e.g. daily cron) and copy backups off the server.
set -euo pipefail

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
[[ "${BACKUP_DEV:-0}" == 1 ]] && COMPOSE=(docker compose)
DEST="${1:-./backups}/$(date -u +%Y%m%dT%H%M%SZ)"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p "$DEST"
chmod 700 "$DEST"

echo "Database → $DEST/db.dump"
"${COMPOSE[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$DEST/db.dump"

echo "Media → $DEST/media.tar.gz"
"${COMPOSE[@]}" exec -T api tar -C /app/media -czf - . > "$DEST/media.tar.gz"

# Sanity check: the dump must contain the orders table. (Read the whole listing first:
# with pipefail, "grep -q" closing the pipe early would look like a failure.)
listing=$("${COMPOSE[@]}" exec -T postgres pg_restore --list < "$DEST/db.dump")
grep -q "TABLE DATA public orders" <<<"$listing" || { echo "Backup looks incomplete!" >&2; exit 1; }

find "$(dirname "$DEST")" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} +
echo "Done: $(du -sh "$DEST" | cut -f1)"
