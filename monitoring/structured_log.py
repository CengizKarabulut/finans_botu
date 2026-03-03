"""JSON structured logging for ELK/Loki compatibility."""
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """Log kayıtlarını JSON formatında yazar."""
    
    def __init__(self, extra_fields: Dict[str, Any] = None):
        super().__init__()
        self.extra_fields = extra_fields or {}
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Exception info ekle
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Extra fields ekle
        log_entry.update(self.extra_fields)
        
        # Context data ekle (eğer record'a eklenmişse)
        if hasattr(record, "context"):
            log_entry["context"] = record.context
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)

def setup_structured_logging(log_file: str = "logs/bot.json", 
                            console: bool = True,
                            extra_fields: Dict[str, Any] = None):
    """Structured JSON logging ayarlarını yap."""
    import os
    from logging.handlers import RotatingFileHandler
    
    # Logger ayarları
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    
    # Mevcut handler'ları temizle
    root.handlers = []
    
    # JSON file handler
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(JSONFormatter(extra_fields))
        file_handler.setLevel(logging.INFO)
        root.addHandler(file_handler)
    
    # Console handler (insan-okunabilir, JSON değil)
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        console_handler.setLevel(logging.INFO)
        root.addHandler(console_handler)
    
    # Third-party logger'ları sessize al
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
