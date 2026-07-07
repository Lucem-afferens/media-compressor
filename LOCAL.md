# Локальный запуск Media Compressor

> **Проще всего:** [установка в один клик](README.md#установка-в-один-клик) — `curl … | bash` или `./install.sh` из репозитория.

Команды для ручного запуска на своей машине (macOS / Linux; на Windows — PowerShell, WSL или Docker).

## Требования

- **Python 3.12+** (подойдёт 3.11+)
- **ffmpeg** в `PATH` — для видео и аудио:

```bash
brew install ffmpeg   # macOS
sudo apt install ffmpeg   # Debian/Ubuntu
```

- Зависимости Python из `requirements.txt` (Pillow, OpenCV headless — для изображений и inpaint)

## Вариант 1: venv

Из корня репозитория (`media-compressor`):

```bash
cd /path/to/media-compressor
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Установка:

```bash
pip install -r requirements.txt
```

Опционально — вкладка **«Текст»** (faster-whisper):

```bash
pip install -r requirements-transcribe.txt
```

При первом запуске скачается модель Whisper (~150 MB для `base`).

### Запуск

```bash
uvicorn app:app --host 127.0.0.1 --port 8090
```

С автоперезагрузкой при разработке:

```bash
uvicorn app:app --host 127.0.0.1 --port 8090 --reload
```

- UI: **http://127.0.0.1:8090**
- Swagger: **http://127.0.0.1:8090/docs**

Останов: **Ctrl+C**

### Проверка

```bash
curl -s http://127.0.0.1:8090/health
```

Ожидается JSON с полями `status`, `ffmpeg`, `pillow`, `max_upload_bytes`.

## Вариант 2: Docker

```bash
docker compose up -d --build
```

Порт **8090** снаружи → **8000** в контейнере: **http://localhost:8090**

Пересборка после изменений:

```bash
docker compose up -d --build
```

Останов:

```bash
docker compose down
```

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `MAX_UPLOAD_MB` | Лимит одного файла (MiB), по умолчанию 2048 |
| `MAX_IMAGE_BATCH` | Макс. изображений в ZIP (1–100), по умолчанию 40 |
| `MAX_IMAGE_MEGAPIXELS` | Лимит мегапикселей, по умолчанию 50 |
| `FFMPEG_TIMEOUT_SEC` | Таймаут ffmpeg (0 = без лимита) |
| `FFMPEG_LOGLEVEL` | `error`, `warning`, `info`, … |
| `MEDIA_COMPRESS_TMPDIR` | Каталог временных файлов |

Пример:

```bash
MAX_UPLOAD_MB=512 uvicorn app:app --host 127.0.0.1 --port 8090
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
```

## Частые проблемы

- **404 на новых маршрутах** — перезапустите uvicorn или используйте `--reload`.
- **Видео / аудио не работают** — проверьте `ffmpeg -version` и поле `ffmpeg` в `/health`.
- **Изображения недоступны** — `pip install pillow opencv-python-headless` в активном venv.
