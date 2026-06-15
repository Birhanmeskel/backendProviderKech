#!/bin/sh
set -e

# Named volumes (media, celerybeat) are created as root; the app runs as appuser.
for dir in /app/media /app/celerybeat; do
  mkdir -p "$dir"
  chown -R appuser:appuser "$dir" 2>/dev/null || chmod -R a+rwX "$dir" 2>/dev/null || true
done

if [ "$(id -u)" = "0" ]; then
  exec gosu appuser "$@"
fi

exec "$@"
