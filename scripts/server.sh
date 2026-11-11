#!/usr/bin/env bash
# Ubuntu server operations. Git pull is deliberately a separate, visible step.
set -Eeuo pipefail
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
ACTION="${1:-status}"
ENV_FILE="${2:-ubuntu.env}"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing $ENV_FILE. Copy ubuntu.env.example to ubuntu.env and set the server LAN address." >&2
    exit 1
fi
command -v docker >/dev/null || { echo 'Install Docker Engine and the Compose plugin first.' >&2; exit 1; }
dc() { docker compose --env-file "$ENV_FILE" "$@"; }
dc version >/dev/null
dc config --quiet

backup() (
    local container restart=false result archive
    container="$(dc ps -a -q web)"
    [[ -n "$container" ]] || { echo 'No deployment found. Run start for the first installation.' >&2; exit 1; }
    mkdir -p backups
    archive="backups/meosar-data-$(date -u +%Y%m%dT%H%M%SZ)-$$.tar.gz"
    if [[ "$(docker inspect --format '{{.State.Running}}' "$container")" == true ]]; then
        restart=true
    fi
    trap 'result=$?; if [[ "$restart" == true ]]; then dc up -d --no-build --wait --wait-timeout 180 web || result=1; fi; exit "$result"' EXIT
    dc stop web
    # A stopped writer gives a consistent archive. No data is migrated or deleted.
    dc run --rm --no-deps -T web python -c \
        'import sys,tarfile; a=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz"); a.add("/data",arcname="."); a.close()' \
        > "$archive.partial"
    tar -tzf "$archive.partial" >/dev/null
    mv -- "$archive.partial" "$archive"
    echo "Backup saved: $PROJECT_DIR/$archive"
)

record_deployment() {
    mkdir -p .deployment
    if [[ -f .deployment/deployed-commit ]]; then
        cp .deployment/deployed-commit .deployment/previous-commit
    fi
    git rev-parse HEAD > .deployment/deployed-commit
    date -u +%Y-%m-%dT%H:%M:%SZ > .deployment/deployed-at
    echo "Healthy deployment: $(cat .deployment/deployed-commit)"
    dc ps
}

case "$ACTION" in
    start)
        dc up -d --build --wait --wait-timeout 180 web
        record_deployment
        ;;
    update)
        [[ -z "$(git status --porcelain)" ]] || {
            echo 'Repository has local changes. Commit or resolve them before updating; nothing was overwritten.' >&2
            exit 1
        }
        echo 'Wait for active calculations and video exports to finish before updating.'
        backup
        dc up -d --build --wait --wait-timeout 180 web
        record_deployment
        ;;
    backup) backup ;;
    status) dc ps ;;
    logs) dc logs --tail=100 web ;;
    *) echo 'Usage: bash scripts/server.sh {start|update|backup|status|logs} [ubuntu.env]' >&2; exit 2 ;;
esac
