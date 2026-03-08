"""
db.py — SQLite veritabanı yönetimi.
✅ MİMARİ GÜNCELLEME - Singleton Connection Pool ve Decimal (TEXT) Hassasiyeti.
✅ DÜZELTİLDİ - asyncio import eklendi, eksik CRUD fonksiyonları tamamlandı.
"""
import os
import asyncio
import aiosqlite
import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal

from config import settings

log = logging.getLogger("finans_botu")


class DBPool:
    """Singleton Database Connection — Bağlantı sızıntılarını (leak) önler."""
    _db: Optional[aiosqlite.Connection] = None
    _lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Lazy lock initialization — event loop olmadan hata vermez."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get_db(cls) -> aiosqlite.Connection:
        async with cls._get_lock():
            if cls._db is None:
                os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
                cls._db = await aiosqlite.connect(settings.DB_PATH)
                cls._db.row_factory = aiosqlite.Row
                # ✅ WAL mode — concurrent read + write desteği
                await cls._db.execute("PRAGMA journal_mode=WAL")
                await cls._db.execute("PRAGMA busy_timeout=5000")
                log.info(f"🗄️ Veritabanı bağlantısı açıldı: {settings.DB_PATH}")
            return cls._db

    @classmethod
    async def close(cls):
        lock = cls._get_lock()
        async with lock:
            if cls._db:
                await cls._db.close()
                cls._db = None
                log.info("🗄️ Veritabanı bağlantısı kapatıldı.")


# ═══════════════════════════════════════════════════════════════
# VERİTABANI BAŞLATMA
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
    log.info("✅ Veritabanı tabloları hazır.")


async def close_db():
    await DBPool.close()


# ═══════════════════════════════════════════════════════════════
# KULLANICI İŞLEMLERİ
# ═══════════════════════════════════════════════════════════════

async def kullanici_kaydet(user_id: int, username: str):
    """Kullanıcıyı veritabanına kaydeder (varsa günceller)."""
    db = await DBPool.get_db()
    await db.execute(
        "INSERT OR IGNORE INTO kullanicilar (user_id, username) VALUES (?, ?)",
        (user_id, username)
    )
    await db.commit()


async def kullanici_dil_guncelle(user_id: int, lang: str):
    """Kullanıcının dil tercihini günceller."""
    db = await DBPool.get_db()
    await db.execute(
        "UPDATE kullanicilar SET lang = ? WHERE user_id = ?",
        (lang, user_id)
    )
    await db.commit()


async def kullanici_dil_getir(user_id: int) -> str:
    """Kullanıcının dil tercihini getirir."""
    db = await DBPool.get_db()
    async with db.execute("SELECT lang FROM kullanicilar WHERE user_id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
        return row["lang"] if row else "tr"


# ═══════════════════════════════════════════════════════════════
# FAVORİ İŞLEMLERİ
# ═══════════════════════════════════════════════════════════════

async def favori_ekle(user_id: int, sembol: str):
    """Favorilere sembol ekler."""
    db = await DBPool.get_db()
    await db.execute(
        "INSERT OR IGNORE INTO favoriler (user_id, sembol) VALUES (?, ?)",
        (user_id, sembol.upper())
    )
    await db.commit()


async def favori_sil(user_id: int, sembol: str):
    """Favorilerden sembol siler."""
    db = await DBPool.get_db()
    await db.execute(
        "DELETE FROM favoriler WHERE user_id = ? AND sembol = ?",
        (user_id, sembol.upper())
    )
    await db.commit()


async def favori_toggle(user_id: int, sembol: str) -> bool:
    """Favoriyi ekler/çıkarır. True döndürürse eklendi, False ise silindi."""
    db = await DBPool.get_db()
    async with db.execute(
        "SELECT 1 FROM favoriler WHERE user_id = ? AND sembol = ?",
        (user_id, sembol.upper())
    ) as cursor:
        mevcut = await cursor.fetchone()

    if mevcut:
        await favori_sil(user_id, sembol)
        return False
    else:
        await favori_ekle(user_id, sembol)
        return True


async def favorileri_getir(user_id: int) -> List[str]:
    """Kullanıcının favori sembollerini getirir."""
    db = await DBPool.get_db()
    async with db.execute(
        "SELECT sembol FROM favoriler WHERE user_id = ? ORDER BY sembol",
        (user_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [row["sembol"] for row in rows]


# ═══════════════════════════════════════════════════════════════
# UYARI İŞLEMLERİ
# ═══════════════════════════════════════════════════════════════

async def uyari_ekle(user_id: int, sembol: str, tip: str, hedef_deger: str):
    """Yeni uyarı ekler."""
    db = await DBPool.get_db()
    await db.execute(
        "INSERT INTO uyarilar (user_id, sembol, tip, hedef_deger) VALUES (?, ?, ?, ?)",
        (user_id, sembol.upper(), tip, str(hedef_deger))
    )
    await db.commit()


async def uyarilari_getir() -> List[Dict[str, Any]]:
    """Tüm aktif uyarıları getirir."""
    db = await DBPool.get_db()
    async with db.execute("SELECT * FROM uyarilar") as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def kullanici_uyarilari_getir(user_id: int) -> List[Dict[str, Any]]:
    """Belirli kullanıcının uyarılarını getirir."""
    db = await DBPool.get_db()
    async with db.execute(
        "SELECT * FROM uyarilar WHERE user_id = ? ORDER BY tarih DESC",
        (user_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def uyari_sil(uyari_id: int, user_id: int = None):
    """Uyarıyı siler. user_id verilmişse yetkilendirme kontrolü yapar."""
    db = await DBPool.get_db()
    if user_id is not None:
        # ✅ GÜVENLİK: Sadece kendi uyarısını silebilir
        await db.execute(
            "DELETE FROM uyarilar WHERE id = ? AND user_id = ?",
            (uyari_id, user_id)
        )
    else:
        # Sistem tarafından çağrılıyorsa (alert_motoru) user_id kontrolü yok
        await db.execute("DELETE FROM uyarilar WHERE id = ?", (uyari_id,))
    await db.commit()


# ═══════════════════════════════════════════════════════════════
# PORTFÖY İŞLEMLERİ
# ═══════════════════════════════════════════════════════════════

async def portfoy_ekle(user_id: int, sembol: str, miktar: str, maliyet: str):
    """
    Portföye varlık ekler.
    ✅ HASSASİYET: Miktar ve maliyet TEXT olarak saklanır (Decimal precision).
    """
    db = await DBPool.get_db()
    await db.execute(
        "INSERT INTO portfoy (user_id, sembol, miktar, maliyet) VALUES (?, ?, ?, ?)",
        (user_id, sembol.upper(), str(miktar), str(maliyet))
    )
    await db.commit()


async def portfoy_getir(user_id: int) -> List[Dict[str, Any]]:
    """Kullanıcının portföyünü getirir."""
    db = await DBPool.get_db()
    async with db.execute(
        "SELECT * FROM portfoy WHERE user_id = ? ORDER BY sembol",
        (user_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def portfoy_sil(user_id: int, sembol: str):
    """Portföyden sembolü siler."""
    db = await DBPool.get_db()
    await db.execute(
        "DELETE FROM portfoy WHERE user_id = ? AND sembol = ?",
        (user_id, sembol.upper())
    )
    await db.commit()


async def portfoy_guncelle(portfoy_id: int, miktar: str, maliyet: str):
    """Portföy kaydını günceller."""
    db = await DBPool.get_db()
    await db.execute(
        "UPDATE portfoy SET miktar = ?, maliyet = ? WHERE id = ?",
        (str(miktar), str(maliyet), portfoy_id)
    )
    await db.commit()
