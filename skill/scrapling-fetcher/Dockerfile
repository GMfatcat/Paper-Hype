# Scrapling 取文容器 — Mode B 取文 adapter
# build:  docker build -t hype-fetcher .      (run from this scrapling-fetcher/ dir)
# run:    docker run --rm hype-fetcher "<URL>"
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# 連結預覽 meta (og:description) 走 httpx 退路時用得到的基本工具
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget gnupg \
    && rm -rf /var/lib/apt/lists/*

# [fetchers] extra 才會帶入 curl_cffi / playwright / camoufox 等取文相依
RUN pip install "scrapling[fetchers]"

# 下載瀏覽器二進位 + 其 OS 相依（camoufox / playwright chromium）。
# 失敗不擋 build：StealthyFetcher 不可用時 fetch.py 會自動退回 httpx 的 Fetcher（靠 curl_cffi）。
RUN python -m playwright install-deps 2>/dev/null || true
RUN scrapling install || python -m playwright install chromium || true

COPY fetch.py /app/fetch.py
WORKDIR /app
ENTRYPOINT ["python", "fetch.py"]
