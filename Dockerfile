# Controlled Copy: one Python service, served behind Caddy (see compose.yml).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    DATA_DIR=/app/data

WORKDIR /app

# Debian security updates published since the base image was built (build with --pull to
# also start from the newest base image).
RUN apt-get update \
    && apt-get -y upgrade --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Every dependency is pinned with a hash; nothing unpinned is downloaded. pip itself is then
# removed: the app never installs anything at runtime, and the base image's pip carries
# vendored copies of urllib3, msgpack and setuptools that lag behind their security fixes.
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock \
    && pip uninstall -y pip

COPY src ./src
COPY demo-data ./demo-data

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown appuser /app/data \
    && chmod 0700 /app/data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

# Only Caddy can reach this port (internal compose network), so forwarded headers from it are trusted.
# No access log: it would keep query strings and client addresses; the app logs content-free events.
CMD ["python", "-m", "uvicorn", "controlled_copy.app:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header", "--no-access-log"]
