# Media Compressor

Локальный веб-сервис для сжатия **видео**, **аудио** и **изображений** на вашем компьютере. Файлы не покидают машину — всё обрабатывается через ffmpeg, Pillow и OpenCV.

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Возможности

| Режим | Описание |
|-------|----------|
| **Видео** | H.264 / H.265, CRF, preset, масштаб, битрейт аудио |
| **Аудио** | MP3, AAC/M4A, Opus, FLAC; извлечение дорожки из видео |
| **Изображения** | JPEG, PNG, WebP; один файл или пакет (ZIP) |
| **Inpaint** | Удаление объектов по маске (OpenCV Telea / NS) |

**UI:** drag-and-drop, пресеты, прогресс загрузки и кодирования, ETA, отмена операций, превью результата.

**API:** синхронные и асинхронные задачи (`async_mode=true`) с polling прогресса ffmpeg.

## Быстрый старт

### Docker (рекомендуется)

```bash
git clone https://github.com/YOUR_USERNAME/media-compressor.git
cd media-compressor
docker compose up -d --build
```

Откройте **http://localhost:8090**

### Локально

```bash
git clone https://github.com/YOUR_USERNAME/media-compressor.git
cd media-compressor
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8090
```

Требуется **ffmpeg** в `PATH` (`brew install ffmpeg` на macOS).

Подробнее: [LOCAL.md](LOCAL.md)

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
