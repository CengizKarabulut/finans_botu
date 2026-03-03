"""Kullanıcı tercihleri yönetimi."""
import asyncio
import logging
import json
from typing import Optional, Dict, Any

log = logging.getLogger("finans_botu")

# Varsayılan tercihler
DEFAULT_PREFS = {
    "currency": "TRY",  # TRY, USD, EUR
    "default_analiz": "temel",  # temel, teknik, ai
    "notifications": True,
    "language": "tr",  # tr, en
}

PREF_KEYS = list(DEFAULT_PREFS.keys())

async def get_user_prefs(user_id: int) -> Dict[str, Any]:
    """Kullanıcı tercihlerini getir, yoksa varsayılan döndür."""
    from db import get_db_connection
    try:
        async with get_db_connection() as db:
            cursor = await db.execute(
                "SELECT prefs FROM user_prefs WHERE user_id = ?", 
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                stored = json.loads(row[0])
                return {**DEFAULT_PREFS, **stored}
    except Exception as e:
        log.warning(f"get_user_prefs error: {e}")
    
    return DEFAULT_PREFS.copy()

async def set_user_pref(user_id: int, key: str, value: Any) -> bool:
    """Tek bir tercih değerini güncelle."""
    from db import get_db_connection
    if key not in PREF_KEYS:
        log.warning(f"Invalid pref key: {key}")
        return False
    
    try:
        async with get_db_connection() as db:
            cursor = await db.execute(
                "SELECT prefs FROM user_prefs WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                prefs = json.loads(row[0])
            else:
                prefs = {}
            
            prefs[key] = value
            
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

async def ensure_prefs_table():
    """user_prefs tablosunu oluştur (yoksa)."""
    from db import get_db_connection
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
