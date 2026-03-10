"""
config.py — Uygulama ayarları ve konfigürasyon yönetimi.
✅ MİMARİ GÜNCELLEME - Pydantic Settings ile tip güvenliği ve otomatik doğrulama.
"""
import os
import logging
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

log = logging.getLogger("finans_botu")

class Settings(BaseSettings):
    # Bot Ayarları
    BOT_TOKEN: str = Field(default="", description="Telegram Bot Token")
    LOG_LEVEL: str = Field("INFO", description="Log seviyesi (DEBUG, INFO, WARNING, ERROR)")
    
    # API Anahtarları (Opsiyonel)
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    FINNHUB_API_KEY: Optional[str] = None
    COINGECKO_API_KEY: Optional[str] = None
    FMP_API_KEY: Optional[str] = None
    ALPHAVANTAGE_API_KEY: Optional[str] = None
    
    # TradingView Giriş Bilgileri
    TRADINGVIEW_USERNAME: Optional[str] = None
    TRADINGVIEW_PASSWORD: Optional[str] = None
    TRADINGVIEW_CHART_URL: Optional[str] = None  # Kayıtlı layout URL (örn: https://www.tradingview.com/chart/AbCdEfGh/)
    TV_SESSIONID: Optional[str] = None        # Manuel cookie: tarayıcıdan kopyalanır, login'i atlar
    TV_SESSIONID_SIGN: Optional[str] = None   # Manuel cookie: sessionid ile birlikte gerekli
    
    # Zamanlama ve Limitler (Magic Numbers -> Constants)
    ALERT_CHECK_INTERVAL: int = Field(300, description="Uyarı kontrol döngüsü süresi (saniye)")
    CACHE_TTL_PRICE: int = Field(60, description="Fiyat verisi cache süresi")
    CACHE_TTL_PROFILE: int = Field(3600, description="Profil/Bilanço cache süresi")
    CACHE_TTL_NEWS: int = Field(600, description="Haberler cache süresi")
    
    # Veritabanı
    DB_PATH: str = Field("data/finans_bot.db", description="SQLite veritabanı yolu")
    
    # Monitoring & Health
    HEALTH_HOST: str = Field("0.0.0.0", description="Health server host")
    HEALTH_PORT: int = Field(8080, description="Health server port")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def validate_startup(self) -> List[str]:
        """Eksik zorunlu ayarları kontrol et."""
        missing = []
        if not self.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        return missing

    def startup_log(self) -> str:
        """Başlangıçta loglanacak özet."""
        lines = ["🔧 Ayarlar yüklendi:"]
        lines.append(f"   Bot Token:    {'✅' if self.BOT_TOKEN else '❌'}")
        lines.append(f"   Finnhub:      {'✅' if self.FINNHUB_API_KEY else '⚠️'}")
        lines.append(f"   Gemini:       {'✅' if self.GEMINI_API_KEY else '⚠️'}")
        lines.append(f"   TradingView:  {'✅ ' + self.TRADINGVIEW_USERNAME if self.TRADINGVIEW_USERNAME else '⚠️ (grafik: mplfinance fallback)'}")
        lines.append(f"   Log Level:    {self.LOG_LEVEL}")
        lines.append(f"   Health:       http://{self.HEALTH_HOST}:{self.HEALTH_PORT}")
        return "\n".join(lines)

# Global settings örneği
settings = Settings()

def validate_startup():
    """Bot başlarken çalıştır: eksik ayar varsa hata ver."""
    missing = settings.validate_startup()
    if missing:
        raise RuntimeError(f"❌ Eksik ayarlar: {', '.join(missing)}\n.env dosyasını kontrol edin.")
    log.info(settings.startup_log())
