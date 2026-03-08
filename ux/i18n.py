"""
ux/i18n.py — Çoklu dil desteği (Turkish & English).
✅ YENİ ÖZELLİK - i18n altyapısı.
"""
from typing import Dict

MESSAGES: Dict[str, Dict[str, str]] = {
    'tr': {
        'welcome': (
            "🚀 <b>Finans Botu’na Hoş Geldiniz!</b>\n\n"
            "Hisse senedi, kripto ve döviz analizleri için emrinizdeyim.\n\n"
            "📌 <b>Temel Komutlar:</b>\n"
            "• <code>/analiz THYAO</code> - Kapsamlı analiz\n"
            "• <code>/grafik BTCUSD</code> - TradingView grafiği\n"
            "• <code>/tahmin AAPL</code> - AI fiyat tahmini\n"
            "• <code>/trend</code> - Popüler varlıklar\n"
            "• <code>/favoriler</code> - Favori listeniz\n\n"
            "💡 Herhangi bir şey yazarak AI asistanımla sohbet edebilirsiniz."
        ),
        'error_symbol': "❌ Geçersiz sembol formatı.",
        'error_data': "❌ Veri bulunamadı: {symbol}",
        'processing': "⏳ <b>{symbol}</b> verileri işleniyor...",
        'ai_processing': "🤖 <b>{symbol}</b> AI yorumu hazırlanıyor...",
        'chart_processing': "📊 <b>{symbol}</b> grafiği hazırlanıyor, lütfen bekleyin...",
        'chart_success': "📈 {symbol} TradingView Grafiği",
        'chart_error': "❌ {symbol} grafiği çekilemedi. Sembolü kontrol edin.",
        'ai_error': "Üzgünüm, şu an hiçbir AI motoruna ulaşılamıyor. Lütfen API anahtarlarınızı kontrol edin."
    },
    'en': {
        'welcome': (
            "🚀 <b>Welcome to Finance Bot!</b>\n\n"
            "I am at your service for stock, crypto, and currency analysis.\n\n"
            "📌 <b>Basic Commands:</b>\n"
            "• <code>/analiz THYAO</code> - Comprehensive analysis\n"
            "• <code>/grafik BTCUSD</code> - TradingView chart\n"
            "• <code>/tahmin AAPL</code> - AI price prediction\n"
            "• <code>/trend</code> - Popular assets\n"
            "• <code>/favoriler</code> - Your favorite list\n\n"
            "💡 You can chat with my AI assistant by typing anything."
        ),
        'error_symbol': "❌ Invalid symbol format.",
        'error_data': "❌ Data not found: {symbol}",
        'processing': "⏳ Processing <b>{symbol}</b> data...",
        'ai_processing': "🤖 Preparing <b>{symbol}</b> AI commentary...",
        'chart_processing': "📊 Preparing <b>{symbol}</b> chart, please wait...",
        'chart_success': "📈 {symbol} TradingView Chart",
        'chart_error': "❌ Could not fetch {symbol} chart. Please check the symbol.",
        'ai_error': "Sorry, no AI engine is currently reachable. Please check your API keys."
    }
}

def get_text(key: str, lang: str = 'tr', **kwargs) -> str:
    """Belirtilen dilde metni döndürür."""
    text = MESSAGES.get(lang, MESSAGES['tr']).get(key, MESSAGES['tr'][key])
    return text.format(**kwargs) if kwargs else text
