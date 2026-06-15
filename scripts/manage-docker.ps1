# Run Django management commands against the Postgres/Redis stack started by docker-compose.
# On Windows/macOS/Linux hosts, DATABASE_URL often uses hostname "db"; that only resolves
# inside the Compose network — use this wrapper instead of local `python manage.py`.
#
# Examples:
#   .\scripts\manage-docker.ps1 createsuperuser    # Phone: E.164 e.g. +251983204356 (+ then digits, no spaces)
#   .\scripts\manage-docker.ps1 migrate
#
# Postgres stays on the Docker network only (no host port bind). Avoids blocked ports on Windows.
$ErrorActionPreference = "Stop"
$backendRoot = Split-Path -Parent $PSScriptRoot
Set-Location $backendRoot
docker compose exec -it web python manage.py @args
