"""Tip-güvenli configuration management with Pydantic."""
import os
import logging
from pathlib import Path
from typing import Optional, List
from pydantic import BaseSettings, Field, validator

log = logging.getLogger("finans_botu")

class Settings(BaseSettings):
    """Application settings with validation."""
    
    # Required
    bot_token: str = Field(..., env="BOT_TOKEN")
    
    # Optional API Keys
    finnhub_api_key: Optional[str] = Field(None, env="FINNHUB_API_KEY")
    coingecko_api_key: Optional[str] = Field(None, env="COINGECKO_API_KEY")
    fmp_api_key: Optional[str] = Field(None, env="FMP_API_KEY")
    alphavantage_api_key: Optional[str] = Field(None, env="ALPHAVANTAGE_API_KEY")
    openfigi_api_key: Optional[str] = Field(None, env="OPENFIGI_API_KEY")
    
    # AI Services
    gemini_api_key: Optional[str] = Field(None, env="GEMINI_API_KEY")
    anthropic_api_key: Optional[str] = Field(None, env="ANTHROPIC_API_KEY")
    groq_api_key: Optional[str] = Field(None, env="GROQ_API_KEY")
    
    # TradingView (opsiyonel)
    tradingview_username: Optional[str] = Field(None, env="TRADINGVIEW_USERNAME")
    tradingview_password: Optional[str] = Field(None, env="TRADINGVIEW_PASSWORD")
    
    # App settings
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_dir: Path = Field(Path("logs"), env="LOG_DIR")
    db_path: Path = Field(Path("data/bot.db"), env="DB_PATH")
    
    # Rate limiting
    rate_limit_requests: int = Field(30, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(60, env="RATE_LIMIT_WINDOW")
    
    # Health server
    health_host: str = Field("0.0.0.0", env="HEALTH_HOST")
    health_port: int = Field(8080, env="HEALTH_PORT")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @validator("bot_token")
    def validate_bot_token(cls, v):
        if not v or len(v) < 40:  # Telegram token format
            raise ValueError("Invalid BOT_TOKEN format")
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        valid = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v.upper()
    
    def check_required_keys(self) -> List[str]:
        """Eksik required API key'leri listele."""
        missing = []
        # Şu an sadece BOT_TOKEN required
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        return missing
    
    def to_startup_log(self) -> str:
        """Startup'ta loglanacak config summary."""
        lines = ["🔧 Config loaded:"]
        lines.append(f"   Bot: {'✅' if self.bot_token else '❌'}")
        lines.append(f"   Finnhub: {'✅' if self.finnhub_api_key else '⚠️'}")
        lines.append(f"   CoinGecko: {'✅' if self.coingecko_api_key else '⚠️'}")
        lines.append(f"   FMP: {'✅' if self.fmp_api_key else '⚠️'}")
        lines.append(f"   Gemini: {'✅' if self.gemini_api_key else '⚠️'}")
        lines.append(f"   Log Level: {self.log_level}")
        lines.append(f"   Health: http://{self.health_host}:{self.health_port}")
        return "\n".join(lines)

# Global instance
settings = Settings()

def validate_startup():
    """Startup validation — eksik required config varsa hata fırlat."""
    missing = settings.check_required_keys()
    if missing:
        raise RuntimeError(f"Missing required config: {', '.join(missing)}")
    log.info(settings.to_startup_log())
