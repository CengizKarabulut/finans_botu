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
        # Fiyat ve Teknik Gösterge Uyarıları
        await db.execute("""
            CREATE TABLE IF NOT EXISTS uyarilar (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                sembol      TEXT    NOT NULL,
                tip         TEXT    NOT NULL, -- 'fiyat_ust', 'fiyat_alt', 'rsi_ust', 'rsi_alt'
                hedef_deger REAL    NOT NULL,
                aktif       INTEGER DEFAULT 1,
                olusturma   TEXT DEFAULT (datetime('now'))
            )
        """)
        # Portföy Takibi
        await db.execute("""
            CREATE TABLE IF NOT EXISTS portfoy (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                sembol      TEXT    NOT NULL,
                miktar      REAL    NOT NULL,
                maliyet     REAL    NOT NULL,
                eklendi     TEXT DEFAULT (datetime('now')),
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


# ─────────────────────────────────────────────
#  UYARI (ALERT) FONKSİYONLARI
# ─────────────────────────────────────────────

async def uyari_ekle(user_id: int, sembol: str, tip: str, hedef: float):
    """Yeni bir fiyat veya teknik uyarı ekle."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO uyarilar (user_id, sembol, tip, hedef_deger)
            VALUES (?, ?, ?, ?)
        """, (user_id, sembol.upper(), tip, hedef))
        await db.commit()

async def uyarilari_getir(user_id: int = None) -> list:
    """Kullanıcının veya tüm aktif uyarıları getir."""
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id:
            query = "SELECT * FROM uyarilar WHERE user_id = ? AND aktif = 1"
            params = (user_id,)
        else:
            query = "SELECT * FROM uyarilar WHERE aktif = 1"
            params = ()
        
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            # Convert to list of dicts for easier handling
            cols = [column[0] for column in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

async def uyari_sil(uyari_id: int):
    """Uyarıyı sil."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM uyarilar WHERE id = ?", (uyari_id,))
        await db.commit()

# ─────────────────────────────────────────────
#  PORTFÖY FONKSİYONLARI
# ─────────────────────────────────────────────

async def portfoy_guncelle(user_id: int, sembol: str, miktar: float, maliyet: float):
    """Portföye ekle veya mevcut olanı güncelle."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO portfoy (user_id, sembol, miktar, maliyet)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, sembol) DO UPDATE SET
                miktar  = excluded.miktar,
                maliyet = excluded.maliyet
        """, (user_id, sembol.upper(), miktar, maliyet))
        await db.commit()

async def portfoy_getir(user_id: int) -> list:
    """Kullanıcının portföyünü getir."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM portfoy WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            cols = [column[0] for column in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

async def portfoy_sil(user_id: int, sembol: str):
    """Portföyden varlık sil."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM portfoy WHERE user_id = ? AND sembol = ?", (user_id, sembol.upper()))
        await db.commit()


async def kullanici_sayisi() -> int:
    """Toplam kullanıcı sayısını döndür."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM kullanicilar") as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 0
