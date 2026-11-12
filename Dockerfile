# Bothost-compatible image (also used by local docker compose).
# WORKDIR is outside /app so Bothost bind-mount of repo code does not hide build artifacts.
# Persistent data must live in /app/data (Bothost volume).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    PORT=8080

WORKDIR /usr/src/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data \
    && chmod 777 /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x scripts/entrypoint.sh scripts/bothost_start.sh scripts/backup.sh scripts/restore.sh

EXPOSE 8080

# Local compose overrides command to scripts/entrypoint.sh (fixed port 8741).
# Bothost custom Dockerfile / archive rebuild: Python entry (also works if platform wraps CMD).
CMD ["python", "main.py"]
