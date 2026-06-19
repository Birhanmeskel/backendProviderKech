#!/bin/sh
set -e

# Named volumes (media, celerybeat) are created as root; the app runs as appuser.
for dir in /app/media /app/celerybeat; do
  mkdir -p "$dir"
  chown -R appuser:appuser "$dir" 2>/dev/null || chmod -R a+rwX "$dir" 2>/dev/null || true
done

# Apply DB migrations on startup so deploys self-migrate (Render free tier has
# no shell). Idempotent: a no-op once the schema is up to date.
if [ "$(id -u)" = "0" ]; then
  gosu appuser python manage.py migrate --noinput
  exec gosu appuser "$@"
fi

python manage.py migrate --noinput
exec "$@"
