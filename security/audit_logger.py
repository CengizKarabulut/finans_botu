"""Audit logging for security compliance."""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

log = logging.getLogger("finans_botu")
audit_log = logging.getLogger("finans_botu.audit")

# Audit log handler'ı ayrı dosyaya yönlendir
def setup_audit_logging(log_file: str = "logs/audit.json"):
    """Audit logging ayarlarını yap."""
    import os
    from logging.handlers import RotatingFileHandler
    
    audit_log.setLevel(logging.INFO)
    audit_log.propagate = False  # Root logger'a propagate etme
    
    # JSON file handler
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=10)
    handler.setFormatter(logging.Formatter('%(message)s'))
    audit_log.addHandler(handler)

def log_user_action(user_id: int, username: Optional[str],
                   action: str, resource: str, 
                   details: Optional[Dict] = None,
                   status: str = "success",
                   ip_address: Optional[str] = None):
    """
    Kullanıcı aksiyonunu audit log'a yaz.
    
    Args:
        user_id: Telegram user ID
        username: Telegram username (opsiyonel)
        action: Aksiyon tipi (QUERY, TRADE, CONFIG_CHANGE, etc.)
        resource: Etkilenen kaynak (sembol, komut, vb.)
        details: Ek detaylar (JSON-serializable)
        status: success/failure
        ip_address: Kaynak IP (bot için genelde None)
    """
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "user_action",
        "user": {
            "id": user_id,
            "username": username,
        },
        "action": action,
        "resource": resource,
        "status": status,
        "details": details or {},
        "meta": {
            "bot_version": "1.2.0",
            "ip": ip_address,
        }
    }
    
    audit_log.info(json.dumps(entry, ensure_ascii=False, default=str))

# Convenience wrappers
def log_query(user_id: int, username: str, symbol: str, query_type: str):
    log_user_action(user_id, username, "QUERY", symbol, {"type": query_type})

def log_trade_action(user_id: int, username: str, symbol: str, 
                    action: str, amount: float, price: float):
    log_user_action(user_id, username, "TRADE", symbol, {
        "action": action, "amount": amount, "price": price
    })

def log_config_change(user_id: int, username: str, setting: str, 
                     old_value: Any, new_value: Any):
    log_user_action(user_id, username, "CONFIG_CHANGE", setting, {
        "old_value": old_value, "new_value": new_value
    })

def log_auth_attempt(user_id: int, username: str, success: bool, reason: str = ""):
    log_user_action(user_id, username, "AUTH", "login", 
                   {"success": success, "reason": reason},
                   status="success" if success else "failure")

def log_security_event(user_id: Optional[int], event_type: str, 
                      description: str, severity: str = "medium"):
    """Güvenlik olayı logla (rate limit, invalid input, vb.)."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "security_event",
        "severity": severity,
        "description": description,
        "user_id": user_id,
        "meta": {"bot_version": "1.2.0"}
    }
    audit_log.warning(json.dumps(entry, ensure_ascii=False, default=str))
