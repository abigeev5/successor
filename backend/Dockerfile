# Backend and worker share this image (decision D-022: build context is the repo root).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# ffmpeg — audio and frames of screen recordings; Tesseract (rus+eng) — OCR for personal data on screenshots.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.11.32 \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /data /home/app/.cache/huggingface \
    && chown -R app:app /data /home/app/.cache

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY seed/ /app/seed/
COPY eval/ /app/eval/
RUN uv sync --frozen --no-dev

USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
