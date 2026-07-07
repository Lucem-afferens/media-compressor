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
| `TRANSCRIBE_TIER` | `degraded` | `full` |
| `WHISPER_MODEL` | `base` | `large-v3` |
| `MAX_TRANSCRIBE_SEC` | 180 | 3600 |
| `GENIUS_API_TOKEN` | — | опционально |

`PORT` задаёт Render автоматически.

### Транскрипция на Free

Вкладка **«Текст»** работает в **degraded** режиме: модель `base`, до **3 минут** аудио, без Demucs (отделения вокала). Качество песен ниже, чем локально с `TRANSCRIBE_TIER=full`. Для демо и коротких записей достаточно; тяжёлые модели на 512 MB RAM не поместятся.

## Проверка

```bash
curl -s https://YOUR-SERVICE.onrender.com/health | python3 -m json.tool
```

`"deployment": "cloud"`, `"ffmpeg": true`. После обновлений смотрите `"git_commit"` — должен совпадать с GitHub.

## Обновление с GitHub

Push в `main` деплоится автоматически только если Render **реально получает webhook** и **сборка проходит успешно**.

### Как понять, что на Render старая версия

```bash
curl -s https://media-compressor-0w0q.onrender.com/health | python3 -m json.tool
```

| Признак | Старая сборка | Новая |
|---------|---------------|-------|
| Поле `git_commit` | **нет** | `"c92c557"` или новее |
| Вкладка «Аудио» | «Конвертировать и скачать» | «Сжать или конвертировать» |
| Справка над dropzone | нет синего блока | есть «Сжатие и конвертация аудио» |

Сейчас Auto-Deploy «On Commit» в Dashboard **не гарантирует** деплой: часто webhook не срабатывает или сборка падает, а старый контейнер остаётся Live.

### Шаг 1 — Manual Deploy (сразу)

1. [Render Dashboard](https://dashboard.render.com) → сервис `media-compressor-0w0q`
2. Вкладка **Events** — есть ли deploy после последних push? Статус **Failed** или deploy вообще не было?
3. **Manual Deploy** → **Clear build cache & deploy**
4. Дождитесь **Live** (~5–10 мин)
5. Снова `curl …/health` — должно появиться `"git_commit"`

### Шаг 2 — Deploy Hook (надёжный auto-deploy)

1. Render → сервис → **Settings** → **Deploy Hook** → **Create Deploy Hook**
2. GitHub → репозиторий `media-compressor` → **Settings** → **Secrets and variables** → **Actions**
3. New secret: `RENDER_DEPLOY_HOOK` = URL из Render
4. Следующий push в `main` запустит workflow `.github/workflows/render-deploy.yml` и принудительно дернёт деплой

### Шаг 3 — проверить привязку репозитория

**Settings** → **Build & Deploy**:

- Repository: `Lucem-afferens/media-compressor`
- Branch: `main`
- Runtime: **Docker** (не Python)
- Dockerfile Path: `./Dockerfile`

Изменения в `render.yaml` **не применяются** к уже созданному сервису, пока вы не сделаете **Blueprint sync** или не выставите те же поля в Dashboard вручную.

## Railway

Railway после trial требует **платный план** — см. [RAILWAY.md](RAILWAY.md), если уже есть подписка.

## Масштабирование

Держите **1 instance** — in-memory job store не рассчитан на несколько реплик.
