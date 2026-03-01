#!/bin/bash
# ─────────────────────────────────────────────
# Finans Botu Deploy Scripti
# Kullanım: bash deploy.sh
# ─────────────────────────────────────────────

set -e
REPO="https://raw.githubusercontent.com/CengizKarabulut/finans_botu/main"

echo "🔴 Bot durduruluyor..."
kill -9 $(ps aux | grep "main.py" | grep -v grep | awk '{print $2}') 2>/dev/null || true
sleep 2

echo "📦 Bağımlılıklar kontrol ediliyor..."
pip install --break-system-packages -q borsapy yfinance requests 2>/dev/null || true

echo "📥 Dosyalar güncelleniyor..."
for f in main.py veri_motoru.py piyasa_analiz.py analist_motoru.py; do
    python3 -c "import urllib.request; urllib.request.urlretrieve('$REPO/$f', '$f'); print('  ✅ $f')"
done

echo "🔑 API key'leri kontrol ediliyor..."
[ -z "$BOT_TOKEN" ]           && echo "  ⚠️  BOT_TOKEN eksik!"           || echo "  ✅ BOT_TOKEN"
[ -z "$GEMINI_API_KEY" ]      && echo "  ⚠️  GEMINI_API_KEY eksik!"      || echo "  ✅ GEMINI_API_KEY"
[ -z "$GROQ_API_KEY" ]        && echo "  ⚠️  GROQ_API_KEY eksik!"        || echo "  ✅ GROQ_API_KEY"
[ -z "$FINNHUB_API_KEY" ]     && echo "  ⚠️  FINNHUB_API_KEY eksik (haberler kısıtlı)" || echo "  ✅ FINNHUB_API_KEY"
[ -z "$COINGECKO_API_KEY" ]   && echo "  ⚠️  COINGECKO_API_KEY eksik (kripto kısıtlı)" || echo "  ✅ COINGECKO_API_KEY"
[ -z "$FMP_API_KEY" ]         && echo "  ⚠️  FMP_API_KEY eksik (yabancı bilanço kısıtlı)" || echo "  ✅ FMP_API_KEY"
[ -z "$ALPHAVANTAGE_API_KEY" ]&& echo "  ℹ️  ALPHAVANTAGE_API_KEY yok (opsiyonel)" || echo "  ✅ ALPHAVANTAGE_API_KEY"
echo "  ✅ SEC EDGAR (key'siz)"
echo "  ✅ borsapy (key'siz)"
echo "  ✅ OpenFIGI (key'siz)"
echo "  ✅ ApeWisdom (key'siz)"

echo ""
echo "🚀 Bot başlatılıyor..."
nohup python3 -u main.py > bot_log.txt 2>&1 &
sleep 5

echo ""
echo "📋 Son log:"
tail -10 bot_log.txt
echo ""
echo "✅ Deploy tamamlandı! Log: tail -f bot_log.txt"
