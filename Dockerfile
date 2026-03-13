# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for companyScraper (beautifulsoup4, fake-useragent, lxml) and PDF gen
# libsqlcipher-dev: required to build pysqlcipher3 (SQLCipher AES-256 encryption for cloud mode)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev curl libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps chromium

# Bundle companyScraper (company research web scraper)
COPY scrapers/ /app/scrapers/

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app/app.py", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.fileWatcherType=none"]
