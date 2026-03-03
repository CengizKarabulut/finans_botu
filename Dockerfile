# Base image
FROM python:3.11-slim-bookworm

# Çalışma dizini
WORKDIR /app

# Sistem bağımlılıkları (Playwright için gerekli kütüphaneler dahil)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libegl1 \
    libgbm1 \
    libgl1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libopengl0 \
    libwayland-client0 \
    libwayland-egl1 \
    libx11-6 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    libxxf86vm1 \
    xdg-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python bağımlılıkları
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright tarayıcı kurulumu
RUN playwright install chromium

# Uygulama dosyalarını kopyala
COPY . .

# Log ve veri dizinlerini oluştur
RUN mkdir -p logs data

# Port (Health check için)
EXPOSE 8080

# ✅ DOCKER HEALTHCHECK
# Botun içindeki health_server'ı (8080) kontrol eder.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Başlatma komutu
CMD ["python", "main.py"]
