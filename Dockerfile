FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bust Docker layer cache when templates/static change (Render may cache aggressively).
ARG RENDER_GIT_COMMIT=unknown
LABEL org.opencontainers.image.revision=$RENDER_GIT_COMMIT

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY templates ./templates
COPY static ./static
COPY app.py images.py image_tools.py jobs.py ./
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
