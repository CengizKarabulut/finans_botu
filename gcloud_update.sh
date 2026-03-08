#!/bin/bash
# ═══════════════════════════════════════════════
#  Google Cloud VM — Sadece Güncelleme
#  Kullanım: bash gcloud_update.sh
# ═══════════════════════════════════════════════

cd ~/finans_botu

echo "🔴 Bot durduruluyor..."
sudo systemctl stop finans-botu 2>/dev/null || true
sleep 2

echo "📥 Dosyalar güncelleniyor..."
REPO="https://raw.githubusercontent.com/CengizKarabulut/finans_botu/main"
for dosya in main.py veri_motoru.py piyasa_analiz.py analist_motoru.py; do
    python3 -c "
import urllib.request
try:
    urllib.request.urlretrieve('$REPO/$dosya', '$dosya')
    print('  ✅ $dosya')
except Exception as e:
    print(f'  ⚠️  $dosya: {e}')
"
done

echo "🚀 Bot yeniden başlatılıyor..."
sudo systemctl start finans-botu
sleep 4

echo ""
echo "📋 Durum:"
sudo systemctl status finans-botu --no-pager -l | head -20
echo ""
echo "📋 Son loglar:"
tail -15 ~/finans_botu/bot.log
