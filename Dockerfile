# ─── Stage 1: build deps into an isolated prefix ───
FROM python:3.12-slim AS builder

WORKDIR /install
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install/deps -r requirements.txt

# ─── Stage 2: slim runtime, non-root, no pip cache ───
FROM python:3.12-slim

# Non-root user — never run the service as root.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin svc

WORKDIR /app
COPY --from=builder /install/deps /usr/local
COPY app/ ./app/
COPY data/ ./data/

USER svc
EXPOSE 8000

# Healthcheck without curl (not installed) — hits liveness on the loopback.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health',timeout=3).status==200 else 1)"]

CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
