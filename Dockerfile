FROM python:3.12-slim AS base

# libpq is needed at runtime by psycopg even with the [binary] wheel's bundled libs on some
# platforms; kept minimal on purpose - OCR (tesseract-ocr) and Whisper's ffmpeg dependency are
# left OUT by design, matching the app's "honest degradation" model: those features report
# NOT_CONFIGURED rather than being force-installed into every deployment that doesn't need them.
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/civiclens

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini run.py ./
COPY scripts/ scripts/

RUN mkdir -p uploads logs

EXPOSE 8080
ENV HOST=0.0.0.0 PORT=8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Migrations are applied explicitly (docker-compose entrypoint or a deploy step), never implicitly
# on every container start - a partially-applied migration should never happen silently.
CMD ["python", "run.py"]
