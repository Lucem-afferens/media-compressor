FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG RENDER_GIT_COMMIT=unknown
ARG TRANSCRIBE_TIER=degraded
LABEL org.opencontainers.image.revision=$RENDER_GIT_COMMIT

COPY requirements.txt requirements-transcribe.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-transcribe.txt

COPY templates ./templates
COPY static ./static
COPY app.py images.py image_tools.py jobs.py ./
COPY transcription ./transcription
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV TRANSCRIBE_TIER=${TRANSCRIBE_TIER}
ENV WHISPER_MODEL=base
ENV MAX_TRANSCRIBE_SEC=180
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
