#!/bin/bash
# ═══════════════════════════════════════════════
#  Google Cloud VM (e2-micro) — Finans Botu Kurulum
#  Kullanım: bash gcloud_free_setup.sh
# ═══════════════════════════════════════════════

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Finans Botu — GCloud Ücretsiz Kurulum"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─────────────────────────────────────────────
#  1. SİSTEM GÜNCELLEMESİ VE DOCKER KURULUMU
# ─────────────────────────────────────────────
echo ""
echo "📦 [1/5] Sistem güncelleniyor ve Docker kuruluyor..."
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl gnupg git

# Docker GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -qq
sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Current user to docker group
sudo usermod -aG docker $USER

echo "  ✅ Docker kuruldu"

# ─────────────────────────────────────────────
#  2. SWAP ALANI OLUŞTURMA (e2-micro için kritik!)
# ─────────────────────────────────────────────
echo ""
echo "💾 [2/5] Swap alanı oluşturuluyor (RAM yetersizliği için)..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fetc/fstab
    echo "  ✅ 2GB Swap alanı aktif edildi"
else
    echo "  ℹ️  Swap alanı zaten mevcut"
fi

# ─────────────────────────────────────────────
#  3. PROJE DOSYALARI
# ─────────────────────────────────────────────
echo ""
echo "📥 [3/5] Proje dosyaları hazırlanıyor..."
# Eğer repo zaten klonlanmışsa güncelle, yoksa klonla
if [ -d "finans_botu" ]; then
    cd finans_botu
    git pull
else
    git clone https://github.com/CengizKarabulut/finans_botu.git
    cd finans_botu
fi

mkdir -p logs data
echo "  ✅ Dosyalar hazır"

# ─────────────────────────────────────────────
#  4. .ENV DOSYASI OLUŞTUR
# ─────────────────────────────────────────────
echo ""
echo "🔑 [4/5] .env dosyası kontrol ediliyor..."

if [ ! -f .env ]; then
cat > .env << 'ENVEOF'
# Telegram Bot Token (Zorunlu)
BOT_TOKEN=buraya_bot_token

# AI API Keys (En az biri önerilir)
GEMINI_API_KEY=
GROQ_API_KEY=
ANTHROPIC_API_KEY=

# Finansal Veri API Keys (Önerilir)
FINNHUB_API_KEY=
COINGECKO_API_KEY=
FMP_API_KEY=
ALPHAVANTAGE_API_KEY=
OPENFIGI_API_KEY=

# Uygulama Ayarları
LOG_LEVEL=INFO
DB_PATH=data/bot.db
ENVEOF
    echo "  ✅ .env oluşturuldu — Lütfen düzenleyin: nano .env"
else
    echo "  ℹ️  .env zaten mevcut"
fi

# ─────────────────────────────────────────────
#  5. TAMAMLANDI
# ─────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Kurulum Hazır!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  ⚡ SONRAKİ ADIMLAR:"
echo ""
echo "  1. API anahtarlarınızı girin:"
echo "     nano .env"
echo ""
echo "  2. Botu Docker ile başlatın:"
echo "     docker compose -f docker-compose.prod.yml up -d --build"
echo ""
echo "  3. Logları takip edin:"
echo "     docker compose logs -f"
echo ""
echo "  ⚠️  NOT: Docker grubuna eklendiğiniz için değişikliklerin"
echo "  aktif olması için oturumu kapatıp açmanız gerekebilir."
echo "  Veya komutları 'sudo' ile çalıştırabilirsiniz."
