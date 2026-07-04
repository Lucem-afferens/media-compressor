# Media Compressor

Сжатие **видео**, **аудио** и **изображений**. Три варианта:

| | **Локально** | **Railway (облако)** | **Vercel (облако)** |
|---|--------------|----------------------|---------------------|
| **Обработка** | На вашем ПК | На сервере Railway | На сервере Vercel |
| **Приватность** | Файлы не покидают машину | Файлы на сервере | Файлы на сервере |
| **Видео / аудио** | ✓ | ✓ | ✗ |
| **Inpaint** | ✓ | ✓ | ✗ |
| **Лимит файла** | до 2 ГБ | до 512 МБ (настраивается) | ~4 МБ |
| **Запуск** | [Установка](#локальная-версия) | [Railway](#облако-railway--полный-сервис) | [Vercel](#облако-vercel--только-фото) |

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## Локальная версия

Файлы **не отправляются в облако** — ffmpeg, Pillow и OpenCV на вашей машине.

[![Установить](https://img.shields.io/badge/▶_Установить-одной_командой-2563eb?style=for-the-badge&logo=terminal&logoColor=white)](#установка-в-один-клик)

### Установка в один клик

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/Lucem-afferens/media-compressor/main/install.sh | bash
```

**Windows:** `irm …/install.ps1 | iex` · подробнее [LOCAL.md](LOCAL.md)

→ **http://localhost:8090**

### Вручную

```bash
git clone https://github.com/Lucem-afferens/media-compressor.git
cd media-compressor
docker compose up -d --build
```

**Требования:** Docker *или* Python 3.11+ + ffmpeg, порт 8090.

---

## Облако: Railway — полный сервис

> Файлы **загружаются на сервер**. Все режимы: видео, аудио, фото, inpaint, прогресс ffmpeg.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/github?template=https://github.com/Lucem-afferens/media-compressor)

1. Нажмите кнопку → подключите GitHub → Deploy.
2. **Settings → Networking → Generate Domain**.
3. Откройте выданный URL.

Подробнее: [RAILWAY.md](RAILWAY.md) — переменные, ресурсы, troubleshooting.

Рекомендуемые переменные: `MAX_UPLOAD_MB=512`, `FFMPEG_TIMEOUT_SEC=3600`.

---

## Облако: Vercel — только фото

> Лёгкий demo: **только изображения**, лимит ~4 МБ. Без видео и аудио.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FLucem-afferens%2Fmedia-compressor&project-name=media-compressor-cloud)

Использует `cloud_app.py` + `vercel.json`, не полный `app.py`.

---

## API

Swagger (локально / Railway): `/docs`

- `POST /compress` — видео (`?async_mode=true` + `/jobs/{id}/…`)
- `POST /optimize-audio` — аудио
- `POST /optimize-image`, `/optimize-images` — фото
- `POST /inpaint-remove` — inpaint

## Переменные окружения

| Переменная | Локально | Cloud (Railway) |
|------------|----------|-----------------|
| `MAX_UPLOAD_MB` | 2048 | 512 (default) |
| `DEPLOYMENT_MODE` | `local` (auto) | `cloud` (auto на Railway) |
| `FFMPEG_TIMEOUT_SEC` | 0 | 3600 рекомендуется |
| `MEDIA_COMPRESS_TMPDIR` | system temp | `/tmp` |

## Разработка

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
uvicorn app:app --host 127.0.0.1 --port 8090 --reload
```

## Лицензия

[MIT](LICENSE)
