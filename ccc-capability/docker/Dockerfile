FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash capability
WORKDIR /app

COPY --from=builder /root/.local /home/capability/.local
COPY app/ ./app/
COPY static/ ./static/
COPY capability.manifest.json ./capability.manifest.json

ENV PATH=/home/capability/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    CWCC_HOST=0.0.0.0 \
    CWCC_PORT=8000

RUN mkdir -p /data && chown -R capability:capability /app /data
USER capability

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/capability/health').status == 200 else sys.exit(1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
