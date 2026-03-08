#!/bin/bash
# ═══════════════════════════════════════════════
#  Google Cloud VM — Finans Botu Tam Kurulum
#  Kullanım: bash gcloud_setup.sh
# ═══════════════════════════════════════════════

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Finans Botu — GCloud Kurulum Başlıyor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─────────────────────────────────────────────
#  1. SİSTEM GÜNCELLEMESİ
# ─────────────────────────────────────────────
echo ""
echo "📦 [1/6] Sistem güncelleniyor..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip git screen

# ─────────────────────────────────────────────
#  2. PYTHON BAĞIMLILIKLARI
# ─────────────────────────────────────────────
echo ""
echo "🐍 [2/6] Python paketleri kuruluyor..."
pip3 install --break-system-packages -q \
    pyTelegramBotAPI \
    yfinance \
    pandas \
    numpy \
    requests \
    borsapy \
    google-generativeai \
    groq

echo "  ✅ Paketler kuruldu"

# ─────────────────────────────────────────────
#  3. PROJE DOSYALARI
# ─────────────────────────────────────────────
echo ""
echo "📥 [3/6] Proje dosyaları indiriliyor..."

REPO="https://raw.githubusercontent.com/CengizKarabulut/finans_botu/main"
DOSYALAR=(
    "main.py"
    "veri_motoru.py"
    "piyasa_analiz.py"
    "temel_analiz.py"
    "teknik_analiz.py"
    "analist_motoru.py"
    "cache_yonetici.py"
    "sektor_listesi.json"
)

mkdir -p ~/finans_botu
cd ~/finans_botu

for dosya in "${DOSYALAR[@]}"; do
    python3 -c "
import urllib.request, sys
try:
    urllib.request.urlretrieve('$REPO/$dosya', '$dosya')
    print('  ✅ $dosya')
except Exception as e:
    print(f'  ⚠️  $dosya: {e}')
"
done

# ─────────────────────────────────────────────
#  4. .ENV DOSYASI OLUŞTUR
# ─────────────────────────────────────────────
echo ""
echo "🔑 [4/6] API key dosyası oluşturuluyor..."

if [ ! -f .env ]; then
cat > .env << 'ENVEOF'
BOT_TOKEN=buraya_bot_token
GEMINI_API_KEY=buraya_gemini_key
GROQ_API_KEY=buraya_groq_key
FINNHUB_API_KEY=buraya_finnhub_key
COINGECKO_API_KEY=buraya_coingecko_key
FMP_API_KEY=buraya_fmp_key
ALPHAVANTAGE_API_KEY=buraya_alphavantage_key
ENVEOF
    echo "  ✅ .env oluşturuldu — düzenlemeyi unutma: nano ~/finans_botu/.env"
else
    echo "  ℹ️  .env zaten mevcut, dokunulmadı"
fi

# ─────────────────────────────────────────────
#  5. SERVİS DOSYASI (systemd — otomatik başlatma)
# ─────────────────────────────────────────────
echo ""
echo "⚙️  [5/6] systemd servisi kuruluyor..."

sudo tee /etc/systemd/system/finans-botu.service > /dev/null << SERVICEEOF
[Unit]
Description=Finans Telegram Botu
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=/home/$(whoami)/finans_botu
EnvironmentFile=/home/$(whoami)/finans_botu/.env
ExecStart=/usr/bin/python3 -u main.py
Restart=always
RestartSec=10
StandardOutput=append:/home/$(whoami)/finans_botu/bot.log
StandardError=append:/home/$(whoami)/finans_botu/bot.log

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl daemon-reload
sudo systemctl enable finans-botu
echo "  ✅ Servis kuruldu (otomatik başlatma aktif)"

# ─────────────────────────────────────────────
#  6. TAMAMLANDI
# ─────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Kurulum tamamlandı!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  ⚡ SONRAKI ADIMLAR:"
echo ""
echo "  1. API key'lerini gir:"
echo "     nano ~/finans_botu/.env"
echo ""
echo "  2. Botu başlat:"
echo "     sudo systemctl start finans-botu"
echo ""
echo "  3. Durumu kontrol et:"
echo "     sudo systemctl status finans-botu"
echo ""
echo "  4. Log takip et:"
echo "     tail -f ~/finans_botu/bot.log"
echo ""
echo "  Diğer komutlar:"
echo "  sudo systemctl stop finans-botu    # Durdur"
echo "  sudo systemctl restart finans-botu # Yeniden başlat"
echo "  sudo systemctl disable finans-botu # Otomatik başlatmayı kapat"
