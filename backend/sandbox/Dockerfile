# Minimal sandbox for executing wireless-comm Python code.
# Build: docker build -t wcai-sandbox ./sandbox
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy scipy matplotlib

# Clear matplotlib font cache so it picks up new fonts
RUN python -c "import matplotlib.font_manager; matplotlib.font_manager._load_fontmanager(try_read_cache=False)"

# Run as nobody — no filesystem write outside /tmp
USER nobody

WORKDIR /code
