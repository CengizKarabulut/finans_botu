#!/bin/bash
# ════════════════════════════════════════
# Finans Botu Başlatma Scripti
# Kullanım: bash baslat.sh
# ════════════════════════════════════════

PROJE_DIZIN="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/venv"

# Renk kodları
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${GREEN}🤖 Finans Botu Başlatılıyor...${NC}"

# 1. Virtual env kontrol
if [ ! -f "$VENV/bin/python" ]; then
    echo -e "${YELLOW}⚙️  Virtual environment oluşturuluyor...${NC}"
    python3.11 -m venv "$VENV"
    echo -e "${YELLOW}📦 Bağımlılıklar kuruluyor...${NC}"
    "$VENV/bin/pip" install --upgrade pip -q
    "$VENV/bin/pip" install -r "$PROJE_DIZIN/requirements.txt" -q
    echo -e "${GREEN}✅ Kurulum tamamlandı.${NC}"
fi

# 2. .env kontrol
if [ ! -f "$PROJE_DIZIN/.env" ]; then
    echo -e "${RED}❌ .env dosyası bulunamadı: $PROJE_DIZIN/.env${NC}"
    exit 1
fi

# 3. Data dizini oluştur
mkdir -p "$PROJE_DIZIN/data"

# 4. Botu başlat
cd "$PROJE_DIZIN"
echo -e "${GREEN}🚀 Bot başlatılıyor... (Durdurmak için Ctrl+C)${NC}"
exec "$VENV/bin/python" main.py
