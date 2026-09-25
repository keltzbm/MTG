#!/usr/bin/env bash
# Runs once, when the codespace is created: uv, the project, and a database
# password. .env lives in the workspace, which survives rebuilds.
set -euo pipefail

curl -LsSf https://astral.sh/uv/install.sh | sh
"$HOME/.local/bin/uv" sync --locked

if [ ! -f .env ]; then
  printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env
fi
