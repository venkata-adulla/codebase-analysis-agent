# Production image — Python FastAPI backend
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    git \
    bash \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x backend/wait-for-services.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Logs: uvicorn + Python unbuffered → stdout/stderr (no log suppression).
# Wait for TCP deps, then Alembic unless SKIP_ALEMBIC_UPGRADE is set, then app (exec for signals).
CMD ["/bin/bash", "-c", "./backend/wait-for-services.sh && case \"${SKIP_ALEMBIC_UPGRADE}\" in 1|true|TRUE|yes|Yes) ;; *) alembic upgrade head ;; esac && exec uvicorn main:app --host 0.0.0.0 --port 8000"]
