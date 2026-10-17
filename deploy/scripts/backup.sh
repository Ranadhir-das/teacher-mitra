#!/usr/bin/env bash
# Root-only, explicitly authorized maintenance-window backup. Never run now.
set -euo pipefail
umask 077
if [[ "${TEACHERMITRA_ALLOW_BACKUP_DOWNTIME:-}" != 1 ]]; then
    echo 'Set TEACHERMITRA_ALLOW_BACKUP_DOWNTIME=1 in the approved maintenance window.' >&2
    exit 1
fi
[[ "$EUID" -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }
exec 9>/run/lock/teachermitra-backup.lock
flock -n 9 || { echo 'Another backup is running.' >&2; exit 1; }
export PGSERVICEFILE=/etc/teachermitra/pg_service.conf
export PGPASSFILE=/etc/teachermitra/pgpass
[[ -r "$PGSERVICEFILE" && -r "$PGPASSFILE" ]]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
destination=/var/backups/teachermitra
mkdir -p "$destination"
chmod 700 "$destination"
staging="$destination/.partial-$stamp"
mkdir "$staging"
was_active=0
if systemctl is-active --quiet teachermitra; then was_active=1; fi
restore_service() {
    if [[ "$was_active" -eq 1 ]]; then systemctl start teachermitra; fi
}
trap restore_service EXIT
systemctl stop teachermitra
if systemctl is-active --quiet teachermitra; then
    echo 'Could not stop writers; backup aborted.' >&2
    exit 1
fi
# No credentials on the command line or in these archives.
pg_dump --dbname=service=teachermitra --format=custom --file="$staging/database.dump"
tar -C /var/lib/teachermitra -czf "$staging/uploads.tar.gz" media private_documents
pg_restore --list "$staging/database.dump" >/dev/null
tar -tzf "$staging/uploads.tar.gz" >/dev/null
readlink -f /srv/teachermitra/current > "$staging/release.txt"
(cd "$staging" && sha256sum database.dump uploads.tar.gz release.txt > SHA256SUMS)
mv "$staging" "$destination/$stamp"
echo "Backup completed: $destination/$stamp"
# No automatic pruning. Copy encrypted snapshots off-host and enforce reviewed retention.
