"""Kullanıcı tercihleri yönetimi."""
import asyncio
import logging
from typing import Optional, Dict, Any
from db import get_db_connection  # Mevcut DB fonksiyonu

log = logging.getLogger("finans_botu")

# Varsayılan tercihler
DEFAULT_PREFS = {
    "currency": "TRY",  # TRY, USD, EUR
    "default_analiz": "temel",  # temel, teknik, ai
    "notifications": True,
    "language": "tr",  # tr, en
    "timezone": "Europe/Istanbul",
}

PREF_KEYS = list(DEFAULT_PREFS.keys())

async def get_user_prefs(user_id: int) -> Dict[str, Any]:
    """Kullanıcı tercihlerini getir, yoksa varsayılan döndür."""
    try:
        async with get_db_connection() as db:
            cursor = await db.execute(
                "SELECT prefs FROM user_prefs WHERE user_id = ?", 
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                import json
                stored = json.loads(row[0])
                # Varsayılanlarla merge et (yeni alanlar için)
                return {**DEFAULT_PREFS, **stored}
    except Exception as e:
        log.warning(f"get_user_prefs error: {e}")
    
    return DEFAULT_PREFS.copy()

async def set_user_pref(user_id: int, key: str, value: Any) -> bool:
    """Tek bir tercih değerini güncelle."""
    if key not in PREF_KEYS:
        log.warning(f"Invalid pref key: {key}")
        return False
    
    try:
        import json
        async with get_db_connection() as db:
            # Mevcut prefs'leri al
            cursor = await db.execute(
                "SELECT prefs FROM user_prefs WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                prefs = json.loads(row[0])
            else:
                prefs = {}
            
            # Güncelle
            prefs[key] = value
            
            # Upsert
            await db.execute(
                """INSERT INTO user_prefs (user_id, prefs) 
                   VALUES (?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET prefs = ?""",
                (user_id, json.dumps(prefs), json.dumps(prefs))
            )
            await db.commit()
            return True
    except Exception as e:
        log.exception(f"set_user_pref error: {e}")
        return False

async def set_user_prefs(user_id: int, prefs: Dict[str, Any]) -> bool:
    """Tüm tercihleri toplu güncelle."""
    try:
        import json
        # Sadece geçerli key'leri al
        filtered = {k: v for k, v in prefs.items() if k in PREF_KEYS}
        
        async with get_db_connection() as db:
            await db.execute(
                """INSERT INTO user_prefs (user_id, prefs) 
                   VALUES (?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET prefs = ?""",
                (user_id, json.dumps(filtered), json.dumps(filtered))
            )
            await db.commit()
            return True
    except Exception as e:
        log.exception(f"set_user_prefs error: {e}")
        return False

# DB migration helper
async def ensure_prefs_table():
    """user_prefs tablosunu oluştur (yoksa)."""
    try:
        async with get_db_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_prefs (
                    user_id INTEGER PRIMARY KEY,
                    prefs TEXT NOT NULL DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
    except Exception as e:
        log.exception(f"ensure_prefs_table error: {e}")
