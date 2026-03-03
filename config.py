"""
config.py — Basit ayarlar yönetimi (pydantic GEREKTİRMEZ)
Kullanım: from config import settings
"""
import os
import logging
from pathlib import Path

log = logging.getLogger("finans_botu")

class Settings:
    """Bot ayarlarını yönetir — basit versiyon."""
    
    def __init__(self):
        # ZORUNLU
        self.bot_token = os.environ.get("BOT_TOKEN", "")
        
        # OPSİYONEL API KEY'LER
        self.finnhub_key = os.environ.get("FINNHUB_API_KEY")
        self.coingecko_key = os.environ.get("COINGECKO_API_KEY")
        self.fmp_key = os.environ.get("FMP_API_KEY")
        self.alphavantage_key = os.environ.get("ALPHAVANTAGE_API_KEY")
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        
        # UYGULAMA AYARLARI
        self.log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        self.log_dir = Path(os.environ.get("LOG_DIR", "logs"))
        self.db_path = Path(os.environ.get("DB_PATH", "data/bot.db"))
        
        # RATE LIMITING
        self.rate_limit_requests = int(os.environ.get("RATE_LIMIT_REQUESTS", "30"))
        self.rate_limit_window = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
        
        # HEALTH SERVER
        self.health_host = os.environ.get("HEALTH_HOST", "0.0.0.0")
        self.health_port = int(os.environ.get("HEALTH_PORT", "8080"))
    
    def validate(self) -> list:
        """Eksik zorunlu ayarları kontrol et."""
        missing = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        return missing
    
    def startup_log(self) -> str:
        """Başlangıçta loglanacak özet."""
        lines = ["🔧 Ayarlar yüklendi:"]
        lines.append(f"   Bot Token: {'✅' if self.bot_token else '❌'}")
        lines.append(f"   Finnhub:   {'✅' if self.finnhub_key else '⚠️'}")
        lines.append(f"   Gemini:    {'✅' if self.gemini_key else '⚠️'}")
        lines.append(f"   Log Level: {self.log_level}")
        lines.append(f"   Health:    http://{self.health_host}:{self.health_port}")
        return "\n".join(lines)

# Global instance
settings = Settings()

def validate_startup():
    """Bot başlarken çalıştır: eksik ayar varsa hata ver."""
    missing = settings.validate()
    if missing:
        raise RuntimeError(f"❌ Eksik ayarlar: {', '.join(missing)}\n.env dosyasını kontrol edin.")
    logging.getLogger("finans_botu").info(settings.startup_log())
