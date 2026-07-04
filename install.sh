#!/usr/bin/env bash
# Media Compressor — установка в один шаг (macOS / Linux).
# Использование:
#   curl -fsSL https://raw.githubusercontent.com/Lucem-afferens/media-compressor/main/install.sh | bash
#   или из клонированного репо: ./install.sh

set -euo pipefail

REPO="https://github.com/Lucem-afferens/media-compressor.git"
INSTALL_DIR="${MEDIA_COMPRESSOR_DIR:-${HOME}/media-compressor}"
PORT="${MEDIA_COMPRESSOR_PORT:-8090}"

info()  { printf '\033[1;34m→\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m!\033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

ensure_repo() {
  if [[ -f "${INSTALL_DIR}/app.py" ]]; then
    info "Каталог уже есть: ${INSTALL_DIR}"
    cd "${INSTALL_DIR}"
    if [[ -d .git ]]; then
      info "Обновление репозитория…"
      git pull --ff-only origin main 2>/dev/null || git pull --ff-only 2>/dev/null || warn "Не удалось обновить git pull — продолжаем"
    fi
    return
  fi

  have git || fail "Нужен git. Установите: https://git-scm.com/downloads"
  info "Клонирование в ${INSTALL_DIR}…"
  git clone --depth 1 "${REPO}" "${INSTALL_DIR}"
  cd "${INSTALL_DIR}"
}

docker_ready() {
  have docker && docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1
}

install_with_docker() {
  info "Установка через Docker (рекомендуется)…"
  docker compose up -d --build
  ok "Media Compressor запущен"
  echo
  echo "  Откройте в браузере:  http://localhost:${PORT}"
  echo "  Остановить:           cd ${INSTALL_DIR} && docker compose down"
  echo "  Запустить снова:      cd ${INSTALL_DIR} && ./start.sh"
}

ensure_ffmpeg() {
  if have ffmpeg; then
    ok "ffmpeg найден: $(ffmpeg -version 2>&1 | head -1)"
    return
  fi
  warn "ffmpeg не найден — нужен для видео и аудио"
  if have brew; then
    info "Установка ffmpeg через Homebrew…"
    brew install ffmpeg
  elif have apt-get; then
    info "Попытка установить ffmpeg через apt (может запросить пароль sudo)…"
    sudo apt-get update && sudo apt-get install -y ffmpeg
  else
    fail "Установите ffmpeg вручную и запустите ./install.sh снова"
  fi
}

install_local() {
  have python3 || fail "Нужен Python 3.11+. Скачайте: https://www.python.org/downloads/"
  local ver
  ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  info "Python ${ver}"

  ensure_ffmpeg

  if [[ ! -d .venv ]]; then
    info "Создание виртуального окружения…"
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate

  info "Установка Python-зависимостей…"
  pip install -q --upgrade pip
  pip install -q -r requirements.txt

  ok "Зависимости установлены"
  echo
  info "Запуск сервера…"
  PORT="${PORT}" ./start.sh --local
}

main() {
  echo
  echo "  Media Compressor — установка"
  echo "  =========================="
  echo

  ensure_repo

  if docker_ready; then
    install_with_docker
  else
    warn "Docker не найден — локальная установка (Python + ffmpeg)"
    install_local
  fi
}

main "$@"
