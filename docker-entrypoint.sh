#!/bin/sh
set -e

# Named volumes (media, celerybeat) are created as root; the app runs as appuser.
for dir in /app/media /app/celerybeat; do
  mkdir -p "$dir"
  chown -R appuser:appuser "$dir" 2>/dev/null || chmod -R a+rwX "$dir" 2>/dev/null || true
done

# Apply DB migrations on startup so deploys self-migrate (Render free tier has
# no shell). Idempotent: a no-op once the schema is up to date.
#
# Optionally bootstrap an admin user from DJANGO_SUPERUSER_PHONE /
# DJANGO_SUPERUSER_PASSWORD env vars (no shell available on free tier).
# Idempotent: createsuperuser exits non-zero if the user already exists, so
# `|| true` keeps startup from failing on later deploys.
if [ "$(id -u)" = "0" ]; then
  gosu appuser python manage.py migrate --noinput
  gosu appuser python manage.py createsuperuser --noinput || true
  exec gosu appuser "$@"
fi

python manage.py migrate --noinput
python manage.py createsuperuser --noinput || true
exec "$@"
