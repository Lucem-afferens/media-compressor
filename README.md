# Media Compressor

Сжатие **видео**, **аудио** и **изображений**. Два варианта использования:

| | **Локальная версия** | **Облачная (Vercel)** |
|---|----------------------|------------------------|
| **Где обрабатываются файлы** | На вашем компьютере | На сервере Vercel |
| **Приватность** | Файлы не покидают машину | Файлы загружаются на сервер |
| **Режимы** | Видео, аудио, фото, inpaint | Только фото |
| **Лимит файла** | до 2 ГБ (настраивается) | ~4 МБ |
| **Установка** | Docker / скрипт / Python | [Deploy на Vercel](#облачная-версия-vercel) |

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## Локальная версия

Локальный веб-сервис: файлы **не отправляются в облако**, всё через ffmpeg, Pillow и OpenCV на вашей машине.

[![Установить](https://img.shields.io/badge/▶_Установить-одной_командой-2563eb?style=for-the-badge&logo=terminal&logoColor=white)](#установка-в-один-клик)

### Требования

| Способ | Что нужно | Время первого запуска |
|--------|-----------|------------------------|
| **Установка в один клик** | macOS / Linux: git; Docker *или* Python 3.11+ и ffmpeg | 2–5 мин |
| **Docker** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) + Docker Compose | 2–5 мин |
| **Python** | Python 3.11+, ffmpeg в `PATH`, ~500 МБ на venv | 1–3 мин |
| **Windows** | Docker Desktop + Git | 2–5 мин |

**Общее:** свободный порт **8090**, место на диске (до 2 ГБ на файл по умолчанию).

**Без ffmpeg** UI откроется, но видео и аудио не работают — фото и inpaint доступны.

### Установка в один клик

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/Lucem-afferens/media-compressor/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/Lucem-afferens/media-compressor/main/install.ps1 | iex
```

→ **http://localhost:8090**

Повторный запуск: `~/media-compressor/start.sh`

### Быстрый старт (вручную)

```bash
git clone https://github.com/Lucem-afferens/media-compressor.git
cd media-compressor
docker compose up -d --build
# или: pip install -r requirements.txt && uvicorn app:app --host 127.0.0.1 --port 8090
```

Подробнее: [LOCAL.md](LOCAL.md)

### Возможности (локально)

| Режим | Описание |
|-------|----------|
| **Видео** | H.264 / H.265, CRF, preset, масштаб |
| **Аудио** | MP3, AAC/M4A, Opus, FLAC |
| **Изображения** | JPEG, PNG, WebP; один файл или ZIP |
| **Inpaint** | Удаление объектов по маске (OpenCV) |

Прогресс загрузки и кодирования, ETA, отмена, async jobs с polling ffmpeg.

---

## Облачная версия (Vercel)

> **Важно:** в облаке файлы **загружаются на сервер** Vercel для обработки. Это не анонимный и не офлайн-режим.
> Видео, аудио и inpaint **не поддерживаются** — только оптимизация изображений (лимит ~4 МБ на запрос).

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FLucem-afferens%2Fmedia-compressor&project-name=media-compressor-cloud&env=MAX_UPLOAD_MB&env=MAX_IMAGE_BATCH&env=MAX_IMAGE_MEGAPIXELS&envDescription=Cloud%20limits%20(optional)&envLink=https%3A%2F%2Fgithub.com%2FLucem-afferens%2Fmedia-compressor%23%25D0%25BE%25D0%25B1%25D0%25BB%25D0%25B0%25D1%2587%25D0%25BD%25D0%25B0%25D1%258F-%25D0%25B2%25D0%25B5%25D1%2580%25D1%2581%25D0%25B8%25D1%258F-vercel)

После деплоя Vercel использует `cloud_app.py` (см. `vercel.json`), а не полный `app.py`.

**Почему не весь функционал в облаке?** Vercel — serverless: нет ffmpeg, лимит ~4.5 МБ на запрос, таймаут до 60–300 с, нет фоновых job store. Видеокодирование туда не переносится.

Переменные для облака:

| Переменная | По умолчанию (cloud) |
|------------|----------------------|
| `MAX_UPLOAD_MB` | 4 |
| `MAX_IMAGE_BATCH` | 8 |
| `MAX_IMAGE_MEGAPIXELS` | 20 |

---

## Проверка (локально)

```bash
curl -s http://localhost:8090/health | python3 -m json.tool
```

Swagger: **http://localhost:8090/docs**

## API (локально)

### Видео — `POST /compress`

```bash
curl -L -F "file=@input.mp4" \
  "http://localhost:8090/compress?codec=h264&crf=23&preset=medium" \
  -o output.mp4
```

Async: `?async_mode=true` → `GET /jobs/{id}/progress`, `GET /jobs/{id}/result`

### Изображения — `POST /optimize-image`, `POST /optimize-images`

### Inpaint — `POST /inpaint-remove`

### Аудио — `POST /optimize-audio`

## Переменные окружения (локально)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `MAX_UPLOAD_MB` | 2048 | Лимит загрузки (MiB) |
| `MAX_IMAGE_BATCH` | 40 | Макс. файлов в пакете |
| `MAX_IMAGE_MEGAPIXELS` | 50 | Бюджет мегапикселей |
| `FFMPEG_TIMEOUT_SEC` | 0 | Таймаут ffmpeg |
| `MEDIA_COMPRESS_TMPDIR` | system temp | Временные файлы |

## Разработка

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
uvicorn app:app --host 127.0.0.1 --port 8090 --reload
```

```
app.py          — локальный FastAPI (полный)
cloud_app.py    — облачный FastAPI (только фото)
jobs.py         — async jobs, ffmpeg progress
images.py       — оптимизация изображений
vercel.json     — деплой на Vercel
```

## Лицензия

[MIT](LICENSE)
