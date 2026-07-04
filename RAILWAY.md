# Деплой на Railway (полный сервис)

> **Trial истёк?** Railway сейчас требует платный план. Бесплатная альтернатива с полным функционалом: **[Render](RENDER.md)**.

На Railway работает **весь** Media Compressor: видео, аудио, изображения, inpaint, async jobs с прогрессом ffmpeg.

> Файлы **загружаются на сервер** Railway для обработки. UI показывает это явно — без обещаний «локальной приватности».

## Быстрый деплой

1. Войдите на [railway.com](https://railway.com) и создайте **New Project → GitHub Repo**.
2. Выберите репозиторий `Lucem-afferens/media-compressor`, ветку `main`.
3. Railway обнаружит `Dockerfile` и `railway.toml`, соберёт образ с ffmpeg и OpenCV.
4. В **Settings → Networking** включите **Generate Domain** — получите публичный URL.
5. Откройте URL в браузере.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/github?template=https://github.com/Lucem-afferens/media-compressor)

## Рекомендуемые переменные

В **Variables** сервиса:

| Переменная | Рекомендуется | Описание |
|------------|---------------|----------|
| `DEPLOYMENT_MODE` | `cloud` | Облачный UI (авто, если задан `RAILWAY_*`) |
| `MAX_UPLOAD_MB` | `512` | Лимит одного файла (по умолчанию 512 в cloud) |
| `MAX_IMAGE_BATCH` | `20` | Файлов в пакете изображений |
| `FFMPEG_TIMEOUT_SEC` | `3600` | Таймаут кодирования (сек) |
| `FFMPEG_LOGLEVEL` | `error` | Логи ffmpeg |

`PORT` задаёт Railway автоматически — не переопределяйте.

## Ресурсы

- **Минимум:** 2 vCPU, 2 GB RAM — для коротких роликов и фото.
- **Видео H.265 / длинные файлы:** 4+ GB RAM, Pro-план.
- **Масштабирование:** держите **1 реplica** — job store in-memory, горизонтальное масштабирование без общего хранилища задач не поддерживается.

## Проверка

```bash
curl -s https://YOUR-APP.up.railway.app/health | python3 -m json.tool
```

Ожидается `"deployment": "cloud"`, `"ffmpeg": true`, `"pillow": true`.

## Локально vs Railway vs Vercel

| | Локально | Railway | Vercel |
|---|----------|---------|--------|
| Видео / аудио | ✓ | ✓ | ✗ |
| Inpaint | ✓ | ✓ | ✗ |
| Приватность | на вашем ПК | файлы на сервере | файлы на сервере |
| Лимит файла | до 2 ГБ | настраивается | ~4 МБ |

## Обновление

Push в `main` → Railway пересобирает и деплоит автоматически (если включён auto-deploy).

## Troubleshooting

- **502 / health fail** — дождитесь окончания сборки; проверьте логи Deploy.
- **413 file too large** — увеличьте `MAX_UPLOAD_MB` или уменьшите файл.
- **Timeout при видео** — задайте `FFMPEG_TIMEOUT_SEC`, увеличьте RAM/CPU на Railway.
