# Minimal sandbox for executing wireless-comm Python code.
# Build: docker build -t wcai-sandbox ./sandbox
FROM python:3.12-slim

RUN pip install --no-cache-dir numpy scipy matplotlib

# Run as nobody — no filesystem write outside /tmp
USER nobody

WORKDIR /code
