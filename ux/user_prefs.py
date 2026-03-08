"""Kullanıcı tercihleri yönetimi — Basit versiyon."""
import logging
from typing import Optional, Dict, Any

log = logging.getLogger("finans_botu")

# Varsayılan tercihler
DEFAULT_PREFS: Dict[str, Any] = {
    "currency": "TRY",
    "default_analiz": "temel",
    "notifications": True,
    "language": "tr",
}

PREF_KEYS = list(DEFAULT_PREFS.keys())

# Basit in-memory cache (bot restart'ında sıfırlanır)
_user_prefs_cache: Dict[int, Dict[str, Any]] = {}

async def get_user_prefs(user_id: int) -> Dict[str, Any]:
    """Kullanıcı tercihlerini getir, yoksa varsayılan döndür."""
    if user_id in _user_prefs_cache:
        return _user_prefs_cache[user_id]
    
    # Şimdilik varsayılan döndür (ileri versiyonda DB'den okunabilir)
    prefs = DEFAULT_PREFS.copy()
    _user_prefs_cache[user_id] = prefs
    return prefs

async def set_user_pref(user_id: int, key: str, value: Any) -> bool:
    """Tek bir tercih değerini güncelle."""
    if key not in PREF_KEYS:
        log.warning(f"Invalid pref key: {key}")
        return False
    
    if user_id not in _user_prefs_cache:
        _user_prefs_cache[user_id] = DEFAULT_PREFS.copy()
    
    _user_prefs_cache[user_id][key] = value
    log.debug(f"User {user_id} pref updated: {key}={value}")
    return True

async def ensure_prefs_table():
    """DB tablosu oluştur — basit versiyonda no-op."""
    # İleri versiyonda DB migration eklenebilir
    log.debug("ensure_prefs_table: no-op (simple mode)")
    pass
