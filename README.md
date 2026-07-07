# Media Compressor

Сжатие **видео**, **аудио** и **изображений**.

| | **Локально** | **Render (облако)** | **Railway** | **Vercel** |
|---|--------------|---------------------|-------------|------------|
| **Цена** | бесплатно | **Free tier** | платный план | Free |
| **Приватность** | файлы на ПК | на сервере | на сервере | на сервере |
| **Видео / аудио** | ✓ | ✓ | ✓ | ✗ |
| **Inpaint** | ✓ | ✓ | ✓ | ✗ |
| **Лимит файла** | до 2 ГБ | ~100 МБ (Free) | настраивается | ~4 МБ |

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## Локальная версия

Файлы **не отправляются в облако**.

[![Установить](https://img.shields.io/badge/▶_Установить-одной_командой-2563eb?style=for-the-badge&logo=terminal&logoColor=white)](#установка)

```bash
curl -fsSL https://raw.githubusercontent.com/Lucem-afferens/media-compressor/main/install.sh | bash
```

→ **http://localhost:8090** · подробнее [LOCAL.md](LOCAL.md)

---

## Облако: Render — полный сервис (бесплатно)

> Рекомендуем, если Railway trial истёк. Файлы на сервере, все режимы.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Lucem-afferens/media-compressor)

1. Кнопка → Render → **Create Web Service**
2. Дождитесь сборки Docker
3. Откройте URL `*.onrender.com`

Free: 512 MB RAM, сервис «засыпает» без трафика 15 мин, лимит файла **100 МБ**.  
Подробнее: [RENDER.md](RENDER.md)

---

## Облако: Railway — полный сервис (платно)

> После trial нужен платный план (~$5+/мес).

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/github?template=https://github.com/Lucem-afferens/media-compressor)

[RAILWAY.md](RAILWAY.md)

---

## Облако: Vercel — только фото

Бесплатный demo без видео/аудио, лимит ~4 МБ.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FLucem-afferens%2Fmedia-compressor&project-name=media-compressor-cloud)

---

## API

`/docs` — Swagger · `POST /compress`, `/optimize-audio`, `/optimize-image`, `/inpaint-remove`, `/transcribe`

### Транскрипция (вкладка «Текст»)

Распознавание речи и песен с таймкодами. Установка ASR:

```bash
pip install -r requirements-transcribe.txt
```

Переменные: `TRANSCRIBE_TIER` (`auto`/`full`/`degraded`), `WHISPER_MODEL`, `MAX_TRANSCRIBE_SEC`, `GENIUS_API_TOKEN` (опционально, для текста песен).

## Разработка

```bash
pip install -r requirements-dev.txt && pytest tests/ -q
uvicorn app:app --host 127.0.0.1 --port 8090 --reload
```

## Лицензия

[MIT](LICENSE)
