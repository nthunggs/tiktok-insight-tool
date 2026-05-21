FROM python:3.11-slim-bookworm

# System deps for Chromium on ARM64
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-noto-cjk \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Tell Playwright to skip downloading its own browser, use system Chromium
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/bin
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 5001
CMD ["python", "app.py"]
