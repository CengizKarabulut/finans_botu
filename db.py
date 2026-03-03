"""
db.py — aiosqlite tabanlı asenkron veritabanı yönetimi.
✅ MİMARİ GÜNCELLEME - Singleton Connection Pool, SQL Injection Koruması ve Async-Safe.
"""
import os
import logging
import aiosqlite
from typing import List, Optional, Dict, Any
from datetime import datetime

log = logging.getLogger("finans_botu")

DB_PATH = os.path.join(os.path.dirname(__file__), "finans_bot.db")

class DBPool:
    """Singleton veritabanı bağlantısı — bot boyunca açık kalır ve sızıntıları önler."""
    _conn: Optional[aiosqlite.Connection] = None

    @classmethod
    async def get_conn(cls) -> aiosqlite.Connection:
        if cls._conn is None:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            cls._conn = await aiosqlite.connect(DB_PATH)
            cls._conn.row_factory = aiosqlite.Row
            log.info(f"Veritabanı bağlantısı açıldı: {DB_PATH}")
        return cls._conn

    @classmethod
    async def close(cls):
        if cls._conn:
            await cls._conn.close()
            cls._conn = None
            log.info("Veritabanı bağlantısı kapatıldı.")

async def db_init():
    """Tabloları oluştur (yoksa)."""
    db = await DBPool.get_conn()
    
    # Kullanıcılar
    await db.execute("""
        CREATE TABLE IF NOT EXISTS kullanicilar (
            user_id   INTEGER PRIMARY KEY,
            username  TEXT,
            ilk_giris TEXT DEFAULT (datetime('now')),
            son_giris TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Favoriler
    await db.execute("""
        CREATE TABLE IF NOT EXISTS favoriler (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            sembol    TEXT    NOT NULL,
            eklendi   TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, sembol)
        )
    """)
    
    # Uyarılar
    await db.execute("""
        CREATE TABLE IF NOT EXISTS uyarilar (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            sembol      TEXT    NOT NULL,
            tip         TEXT    NOT NULL, -- 'fiyat_ust', 'fiyat_alt', 'rsi_ust', 'rsi_alt'
            hedef_deger TEXT    NOT NULL,
            aktif       INTEGER DEFAULT 1,
            olusturma   TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Portföy
    await db.execute("""
        CREATE TABLE IF NOT EXISTS portfoy (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            sembol      TEXT    NOT NULL,
            miktar      TEXT    NOT NULL,
            maliyet     TEXT    NOT NULL,
            eklendi     TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, sembol)
        )
    """)
    
    await db.commit()
    log.info("Veritabanı tabloları hazır.")

# ✅ SQL INJECTION KORUMASI: Tüm sorgularda parametreli yapı kullanıldı.

async def kullanici_kaydet(user_id: int, username: str):
    db = await DBPool.get_conn()
    await db.execute("""
        INSERT INTO kullanicilar (user_id, username, son_giris)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            username  = excluded.username,
            son_giris = datetime('now')
    """, (user_id, username))
    await db.commit()

async def favori_ekle(user_id: int, sembol: str):
    db = await DBPool.get_conn()
    await db.execute("""
        INSERT OR IGNORE INTO favoriler (user_id, sembol)
        VALUES (?, ?)
    """, (user_id, sembol.upper()))
    await db.commit()

async def favori_sil(user_id: int, sembol: str):
    db = await DBPool.get_conn()
    await db.execute("""
        DELETE FROM favoriler WHERE user_id = ? AND sembol = ?
    """, (user_id, sembol.upper()))
    await db.commit()

async def favorileri_getir(user_id: int) -> List[str]:
    db = await DBPool.get_conn()
    async with db.execute("""
        SELECT sembol FROM favoriler
        WHERE user_id = ?
        ORDER BY eklendi ASC
    """, (user_id,)) as cursor:
        rows = await cursor.fetchall()
        return [row["sembol"] for row in rows]

async def uyari_ekle(user_id: int, sembol: str, tip: str, hedef: str):
    db = await DBPool.get_conn()
    await db.execute("""
        INSERT INTO uyarilar (user_id, sembol, tip, hedef_deger)
        VALUES (?, ?, ?, ?)
    """, (user_id, sembol.upper(), tip, str(hedef)))
    await db.commit()

async def uyarilari_getir(user_id: int = None) -> List[Dict[str, Any]]:
    db = await DBPool.get_conn()
    if user_id:
        query = "SELECT * FROM uyarilar WHERE user_id = ? AND aktif = 1"
        params = (user_id,)
    else:
        query = "SELECT * FROM uyarilar WHERE aktif = 1"
        params = ()
    
    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def uyari_sil(uyari_id: int):
    db = await DBPool.get_conn()
    await db.execute("DELETE FROM uyarilar WHERE id = ?", (uyari_id,))
    await db.commit()

async def portfoy_guncelle(user_id: int, sembol: str, miktar: str, maliyet: str):
    db = await DBPool.get_conn()
    await db.execute("""
        INSERT INTO portfoy (user_id, sembol, miktar, maliyet)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, sembol) DO UPDATE SET
            miktar  = excluded.miktar,
            maliyet = excluded.maliyet
    """, (user_id, sembol.upper(), str(miktar), str(maliyet)))
    await db.commit()

async def portfoy_getir(user_id: int) -> List[Dict[str, Any]]:
    db = await DBPool.get_conn()
    async with db.execute("SELECT * FROM portfoy WHERE user_id = ?", (user_id,)) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def portfoy_sil(user_id: int, sembol: str):
    db = await DBPool.get_conn()
    await db.execute("DELETE FROM portfoy WHERE user_id = ? AND sembol = ?", (user_id, sembol.upper()))
    await db.commit()

async def close_db():
    await DBPool.close()
