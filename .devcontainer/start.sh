#!/usr/bin/env bash
# Runs on every start: the ~/.pgpass line libpq reads (the home directory
# doesn't survive a rebuild; .env does), then Postgres, started and migrated.
set -euo pipefail

pw="$(sed -n 's/^POSTGRES_PASSWORD=//p' .env)"
line="localhost:5432:*:tcg:$pw"
touch ~/.pgpass
chmod 600 ~/.pgpass
grep -qxF "$line" ~/.pgpass || printf '%s\n' "$line" >> ~/.pgpass

for _ in $(seq 30); do
  docker info > /dev/null 2>&1 && break
  sleep 1
done

"$HOME/.local/bin/uv" run riffle db up
"$HOME/.local/bin/uv" run riffle db upgrade
