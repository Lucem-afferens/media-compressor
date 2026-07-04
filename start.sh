#!/usr/bin/env bash
# Запуск Media Compressor после установки.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

PORT="${MEDIA_COMPRESSOR_PORT:-8090}"
HOST="${MEDIA_COMPRESSOR_HOST:-127.0.0.1}"

docker_ready() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1
}

start_docker() {
  docker compose up -d --build
  echo "→ http://localhost:${PORT}"
}

start_local() {
  [[ -d .venv ]] || { echo "Сначала запустите ./install.sh" >&2; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate
  echo "→ http://${HOST}:${PORT}  (Ctrl+C — остановить)"
  exec uvicorn app:app --host "${HOST}" --port "${PORT}"
}

if [[ "${1:-}" == "--local" ]]; then
  start_local
elif docker_ready && [[ -f docker-compose.yml ]]; then
  start_docker
elif [[ -d .venv ]]; then
  start_local
else
  echo "Запустите сначала: ./install.sh" >&2
  exit 1
fi
