# Деплой на Render (полный сервис, бесплатный tier)

**Рекомендуемая альтернатива Railway**, если trial истёк или нужен бесплатный облачный хостинг.

Полный функционал: видео, аудио, изображения, inpaint, async jobs.

> Файлы **загружаются на сервер** Render. UI показывает облачный режим.

## Быстрый деплой

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Lucem-afferens/media-compressor)

1. Нажмите кнопку → войдите в Render (карта **не обязательна** на Free).
2. Подтвердите репозиторий и настройки из `render.yaml`.
3. **Create Web Service** — сборка Docker (~5–10 мин).
4. Откройте URL вида `https://media-compressor-xxxx.onrender.com`.

Или вручную: **New → Web Service → Connect GitHub → Runtime: Docker → Free**.

## Ограничения Free tier

| | Free на Render |
|---|----------------|
| RAM / CPU | 512 MB / 0.1 CPU |
| Стоимость | $0, карта не нужна |
| Простой | Спит через 15 мин без трафика (~1 мин на пробуждение) |
| Часы | 750 instance-hours / месяц |
| Видео | Короткие ролики, низкое разрешение; тяжёлое кодирование может упасть по RAM |

На Free в `render.yaml` уже стоят консервативные лимиты: `MAX_UPLOAD_MB=100`.

Для серьёзного видео — план **Standard** (2 GB RAM, ~$25/мес) и `MAX_UPLOAD_MB=512`.

## Переменные

| Переменная | Free (default) | Paid |
|------------|----------------|------|
| `DEPLOYMENT_MODE` | `cloud` | `cloud` |
| `MAX_UPLOAD_MB` | 100 | 512+ |
| `FFMPEG_TIMEOUT_SEC` | 1800 | 3600 |
| `MAX_IMAGE_BATCH` | 10 | 20 |

`PORT` задаёт Render автоматически.

## Проверка

```bash
curl -s https://YOUR-SERVICE.onrender.com/health | python3 -m json.tool
```

`"deployment": "cloud"`, `"ffmpeg": true`.

## Railway

Railway после trial требует **платный план** — см. [RAILWAY.md](RAILWAY.md), если уже есть подписка.

## Масштабирование

Держите **1 instance** — in-memory job store не рассчитан на несколько реплик.
