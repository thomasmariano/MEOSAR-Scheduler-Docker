# Official Python base supports Linux amd64 and arm64. Build each platform natively
# or with buildx; do not force an architecture here.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    MEOSAR_DATA_DIR=/data MEOSAR_CONFIG_DIR=/data/config MEOSAR_TLE_DIR=/data/tles MPLBACKEND=Agg
WORKDIR /app
# Server-side encoding; browser clients render the shared compositor frames.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-web.lock.txt ./
RUN python -m pip install --no-cache-dir -r requirements-web.lock.txt \
    && groupadd --gid 10001 meosar \
    && useradd --uid 10001 --gid 10001 --no-create-home meosar \
    && mkdir -p /data && chown meosar:meosar /data
# Explicit allowlist includes the three approved resource-default JSON files.
COPY paths.py version.py ./
COPY config/ config/
COPY core/ core/
COPY satellites/ satellites/
COPY scheduler/ scheduler/
COPY graphs/ graphs/
COPY reports/ reports/
COPY web/ web/
COPY simulation/ simulation/
COPY assets/earth_texture.jpg assets/earth_texture.jpg
COPY assets/SARLogo.png assets/SARLogo.png
COPY assets/SARLogo.ico assets/SARLogo.ico
# COPY preserves host permissions. Atomic desktop configuration saves can be
# owner-only (0600); image files belong to root while the app runs as UID 10001.
# Normalize image resources to readable files/traversable directories only.
RUN find /app -type d -exec chmod 755 {} + \
    && find /app -type f -exec chmod 644 {} +
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"
CMD ["python", "-m", "uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080"]
