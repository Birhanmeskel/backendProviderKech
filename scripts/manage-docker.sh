#!/usr/bin/env bash
# Same as scripts/manage-docker.ps1 — run Django against Compose DB from the host.
# Postgres is not published on localhost; avoids Windows Hyper-V excluded port collisions.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -it web python manage.py "$@"
