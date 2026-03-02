"""
db.py — Kullanıcı ve favori hisse veritabanı (aiosqlite + SQLite)
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "finans_bot.db")


async def db_init():
    """Tabloları oluştur (yoksa)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kullanicilar (
                user_id   INTEGER PRIMARY KEY,
                username  TEXT,
                ilk_giris TEXT DEFAULT (datetime('now')),
                son_giris TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favoriler (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                sembol    TEXT    NOT NULL,
                eklendi   TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, sembol)
            )
        """)
        await db.commit()


async def kullanici_kaydet(user_id: int, username: str):
    """Kullanıcıyı kaydet veya son giriş zamanını güncelle."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO kullanicilar (user_id, username, son_giris)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                son_giris = datetime('now')
        """, (user_id, username))
        await db.commit()


async def favori_ekle(user_id: int, sembol: str):
    """Favoriye hisse ekle (zaten varsa sessizce geç)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO favoriler (user_id, sembol)
            VALUES (?, ?)
        """, (user_id, sembol.upper()))
        await db.commit()


async def favori_sil(user_id: int, sembol: str):
    """Favoriden hisse sil."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            DELETE FROM favoriler WHERE user_id = ? AND sembol = ?
        """, (user_id, sembol.upper()))
        await db.commit()


async def favorileri_getir(user_id: int) -> list:
    """Kullanıcının favori hisse listesini döndür."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT sembol FROM favoriler
            WHERE user_id = ?
            ORDER BY eklendi ASC
        """, (user_id,)) as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def kullanici_sayisi() -> int:
    """Toplam kullanıcı sayısını döndür."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM kullanicilar") as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 0
