"""
db.py — SQLite veritabanı yönetimi.
✅ MİMARİ GÜNCELLEME - Singleton Connection Pool ve Decimal (TEXT) Hassasiyeti.
"""
import os
import aiosqlite
import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal

from config import settings

log = logging.getLogger("finans_botu")

class DBPool:
    """Singleton Database Connection — Bağlantı sızıntılarını (leak) önler."""
    _db: Optional[aiosqlite.Connection] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_db(cls) -> aiosqlite.Connection:
        async with cls._lock:
            if cls._db is None:
                os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
                cls._db = await aiosqlite.connect(settings.DB_PATH)
                cls._db.row_factory = aiosqlite.Row
                log.info(f"🗄️ Veritabanı bağlantısı açıldı: {settings.DB_PATH}")
            return cls._db

    @classmethod
    async def close(cls):
        async with cls._lock:
            if cls._db:
                await cls._db.close()
                cls._db = None
                log.info("🗄️ Veritabanı bağlantısı kapatıldı.")

# ═══════════════════════════════════════════════════════════════
# VERİTABANI İŞLEMLERİ
# ═══════════════════════════════════════════════════════════════

async def db_init():
    """Tabloları oluşturur."""
    db = await DBPool.get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kullanicilar (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            lang TEXT DEFAULT 'tr',
            kayit_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # ✅ HASSASİYET: Miktar ve maliyet TEXT olarak saklanır (Decimal precision).
    await db.execute("""
        CREATE TABLE IF NOT EXISTS portfoy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            sembol TEXT,
            miktar TEXT,
            maliyet TEXT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS favoriler (
            user_id INTEGER,
            sembol TEXT,
            PRIMARY KEY (user_id, sembol)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS uyarilar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            sembol TEXT,
            tip TEXT,
            hedef_deger TEXT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.commit()

async def close_db():
    await DBPool.close()

# Örnek: Kullanıcı Kaydet
async def kullanici_kaydet(user_id: int, username: str):
    db = await DBPool.get_db()
    await db.execute(
        "INSERT OR IGNORE INTO kullanicilar (user_id, username) VALUES (?, ?)",
        (user_id, username)
    )
    await db.commit()

# Örnek: Favori Ekle
async def favori_ekle(user_id: int, sembol: str):
    db = await DBPool.get_db()
    await db.execute(
        "INSERT OR IGNORE INTO favoriler (user_id, sembol) VALUES (?, ?)",
        (user_id, sembol.upper())
    )
    await db.commit()

# Örnek: Uyarıları Getir
async def uyarilari_getir() -> List[Dict[str, Any]]:
    db = await DBPool.get_db()
    async with db.execute("SELECT * FROM uyarilar") as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

# Örnek: Uyarı Sil
async def uyari_sil(uyari_id: int):
    db = await DBPool.get_db()
    await db.execute("DELETE FROM uyarilar WHERE id = ?", (uyari_id,))
    await db.commit()
