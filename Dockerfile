FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PDSS_WORKDIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends rclone ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt
COPY secure_sync ./secure_sync
COPY web ./web
COPY webapp.py ./
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser && mkdir -p /data /config && chown appuser:appuser /data
USER appuser
EXPOSE 8080
CMD ["gunicorn","--workers","2","--threads","2","--timeout","3600","--bind","0.0.0.0:8080","webapp:app"]
