"""JSON structured logging — ELK/Loki uyumlu."""
import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any
from logging.handlers import RotatingFileHandler

class JSONFormatter(logging.Formatter):
    """Logları JSON formatında yazar."""
    
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)

def setup_structured_logging(log_file: str = "logs/bot.json", console: bool = True):
    """Structured logging ayarlarını yap."""
    import os
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = []
    
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(JSONFormatter())
        fh.setLevel(logging.INFO)
        root.addHandler(fh)
    
    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        ch.setLevel(logging.INFO)
        root.addHandler(ch)
