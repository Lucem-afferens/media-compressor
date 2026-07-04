# Media Compressor

Локальный веб-сервис для сжатия **видео**, **аудио** и **изображений** на вашем компьютере. Файлы не покидают машину — всё обрабатывается через ffmpeg, Pillow и OpenCV.

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

[![Установить](https://img.shields.io/badge/▶_Установить-одной_командой-2563eb?style=for-the-badge&logo=terminal&logoColor=white)](#установка-в-один-клик)

## Требования

| Способ | Что нужно | Время первого запуска |
|--------|-----------|------------------------|
| **Установка в один клик** | macOS / Linux: git; Docker *или* Python 3.11+ и ffmpeg | 2–5 мин |
| **Docker вручную** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) + Docker Compose | 2–5 мин |
| **Python вручную** | Python 3.11+, ffmpeg в `PATH`, ~500 МБ на venv | 1–3 мин |
| **Windows** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) + Git | 2–5 мин |

**Общее для всех режимов:** свободный порт **8090**, место на диске под временные файлы (до 2 ГБ на файл по умолчанию).

**Без ffmpeg** UI откроется, но вкладки «Видео» и «Аудио» не работают — изображения и inpaint доступны.

## Установка в один клик

Скопируйте команду в терминал — скрипт сам клонирует репозиторий, поставит зависимости и запустит сервис.

**macOS / Linux** (если есть Docker — использует его; иначе Python + ffmpeg):

```bash
curl -fsSL https://raw.githubusercontent.com/Lucem-afferens/media-compressor/main/install.sh | bash
```

**Windows** (PowerShell, нужен Docker Desktop):

```powershell
irm https://raw.githubusercontent.com/Lucem-afferens/media-compressor/main/install.ps1 | iex
```

После установки откройте **http://localhost:8090**

Повторный запуск (из каталога `~/media-compressor`):

```bash
./start.sh
```

Другой каталог установки: `MEDIA_COMPRESSOR_DIR=/path/to/dir bash install.sh`

## Возможности

| Режим | Описание |
|-------|----------|
| **Видео** | H.264 / H.265, CRF, preset, масштаб, битрейт аудио |
| **Аудио** | MP3, AAC/M4A, Opus, FLAC; извлечение дорожки из видео |
| **Изображения** | JPEG, PNG, WebP; один файл или пакет (ZIP) |
| **Inpaint** | Удаление объектов по маске (OpenCV Telea / NS) |

**UI:** drag-and-drop, пресеты, прогресс загрузки и кодирования, ETA, отмена операций, превью результата.

**API:** синхронные и асинхронные задачи (`async_mode=true`) с polling прогресса ffmpeg.

## Быстрый старт (вручную)

Если предпочитаете установку без скрипта — см. также [LOCAL.md](LOCAL.md).

### Docker (рекомендуется)

```bash
git clone https://github.com/Lucem-afferens/media-compressor.git
cd media-compressor
docker compose up -d --build
```

Откройте **http://localhost:8090**

### Локально

```bash
git clone https://github.com/Lucem-afferens/media-compressor.git
cd media-compressor
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8090
```

Требуется **ffmpeg** в `PATH` (`brew install ffmpeg` на macOS, `sudo apt install ffmpeg` на Linux).

## Проверка

```bash
curl -s http://localhost:8090/health | python3 -m json.tool
curl -s http://localhost:8090/api/settings | python3 -m json.tool
```

Swagger UI: **http://localhost:8090/docs**

## API (кратко)

### Видео — `POST /compress`

```bash
curl -L -F "file=@input.mp4" \
  "http://localhost:8090/compress?codec=h264&crf=23&preset=medium&audio_bitrate_k=128&scale=none" \
  -o output.mp4
```

Асинхронно с прогрессом: `?async_mode=true` → `{ "job_id": "..." }`, затем:

- `GET /jobs/{id}/progress` — процент и ETA
- `GET /jobs/{id}/result` — скачать результат
- `DELETE /jobs/{id}` — отмена

### Изображения

- `POST /optimize-image` — один файл
- `POST /optimize-images` — пакет, ответ ZIP

Параметры: `output`, `quality`, `max_side`, `png_strategy`, `webp_lossless`, `upscale`.

### Inpaint — `POST /inpaint-remove`

Белая маска = зона заплатки. Параметры: `method=telea|ns`, `radius`.

### Аудио — `POST /optimize-audio`

Форматы: MP3, AAC/M4A, Opus, FLAC. Асинхронный режим: `async_mode=true`.

## Параметры видео

| Параметр | Значения |
|----------|----------|
| `codec` | `h264`, `h265` |
| `crf` | 0…51 |
| `preset` | `ultrafast` … `veryslow` |
| `audio_bitrate_k` | 16…512 |
| `scale` | `none`, `1080`, `720`, `480` |

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `MAX_UPLOAD_MB` | 2048 | Лимит загрузки (MiB) |
| `MAX_IMAGE_BATCH` | 40 | Макс. файлов в пакете изображений |
| `MAX_IMAGE_MEGAPIXELS` | 50 | Бюджет мегапикселей на файл |
| `FFMPEG_TIMEOUT_SEC` | 0 | Таймаут ffmpeg (0 = без лимита) |
| `FFMPEG_LOGLEVEL` | `error` | Уровень логов ffmpeg |
| `MEDIA_COMPRESS_TMPDIR` | system temp | Каталог временных файлов |

> `VIDEO_COMPRESS_TMPDIR` по-прежнему поддерживается как устаревший алиас.

## Разработка

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
uvicorn app:app --host 127.0.0.1 --port 8090 --reload
```

Структура:

```
app.py          — FastAPI, маршруты
jobs.py         — async jobs, прогресс ffmpeg
images.py       — оптимизация изображений
image_tools.py  — inpaint (OpenCV)
static/js/      — модульный фронтенд
templates/      — HTML UI
tests/          — pytest
```

## Лицензия

[MIT](LICENSE)
