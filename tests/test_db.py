"""
tests/test_db.py — db.py için unit testler.
✅ DÜZELTİLDİ - Test izolasyonu: Her test kendi DB instance'ını kullanır.
"""
import os
import sys
import pytest
import asyncio
import tempfile

os.environ["BOT_TOKEN"] = "1234567890:TEST_TOKEN"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _fresh_db(tmp_path: str):
    """Temiz bir DB bağlantısı oluşturur."""
    import db as db_module
    # Singleton'ı sıfırla
    await db_module.DBPool.close()
    db_module.DBPool._db = None
    # Yeni DB yolu ayarla
    db_module.settings.DB_PATH = tmp_path
    # DB'yi başlat
    await db_module.db_init()
    return db_module


@pytest.mark.asyncio
async def test_kullanici_kaydet(tmp_path):
    """Kullanıcı kaydı testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")
    # İkinci kez kayıt (INSERT OR IGNORE) hata vermemeli
    await m.kullanici_kaydet(12345, "testuser")
    
    await m.close_db()


@pytest.mark.asyncio
async def test_favori_ekle_getir(tmp_path):
    """Favori ekleme ve getirme testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")
    await m.favori_ekle(12345, "THYAO")
    await m.favori_ekle(12345, "AAPL")

    favoriler = await m.favorileri_getir(12345)
    assert len(favoriler) == 2
    
    await m.close_db()


@pytest.mark.asyncio
async def test_favori_sil(tmp_path):
    """Favori silme testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")
    await m.favori_ekle(12345, "THYAO")
    await m.favori_sil(12345, "THYAO")

    favoriler = await m.favorileri_getir(12345)
    assert len(favoriler) == 0
    
    await m.close_db()


@pytest.mark.asyncio
async def test_favori_toggle(tmp_path):
    """Favori toggle testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")

    # Ekle
    eklendi = await m.favori_toggle(12345, "THYAO")
    assert eklendi is True

    favoriler = await m.favorileri_getir(12345)
    assert len(favoriler) == 1

    # Çıkar
    eklendi = await m.favori_toggle(12345, "THYAO")
    assert eklendi is False

    favoriler = await m.favorileri_getir(12345)
    assert len(favoriler) == 0
    
    await m.close_db()


@pytest.mark.asyncio
async def test_uyari_ekle_getir(tmp_path):
    """Uyarı ekleme ve getirme testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")
    await m.uyari_ekle(12345, "THYAO", "fiyat_ust", "50.00")
    await m.uyari_ekle(12345, "AAPL", "rsi_alt", "30")

    uyarilar = await m.uyarilari_getir()
    assert len(uyarilar) == 2

    kullanici_uyarilari = await m.kullanici_uyarilari_getir(12345)
    assert len(kullanici_uyarilari) == 2
    
    await m.close_db()


@pytest.mark.asyncio
async def test_uyari_sil(tmp_path):
    """Uyarı silme testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")
    await m.uyari_ekle(12345, "THYAO", "fiyat_ust", "50.00")

    uyarilar = await m.kullanici_uyarilari_getir(12345)
    assert len(uyarilar) == 1

    uyari_id = uyarilar[0]['id']
    await m.uyari_sil(uyari_id)

    uyarilar = await m.kullanici_uyarilari_getir(12345)
    assert len(uyarilar) == 0
    
    await m.close_db()


@pytest.mark.asyncio
async def test_portfoy_ekle_getir(tmp_path):
    """Portföy ekleme ve getirme testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")
    await m.portfoy_ekle(12345, "THYAO", "100", "45.50")
    await m.portfoy_ekle(12345, "AAPL", "10", "150.00")

    portfoy = await m.portfoy_getir(12345)
    assert len(portfoy) == 2

    semboller = [v['sembol'] for v in portfoy]
    assert "THYAO" in semboller
    assert "AAPL" in semboller
    
    await m.close_db()


@pytest.mark.asyncio
async def test_portfoy_sil(tmp_path):
    """Portföy silme testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")
    await m.portfoy_ekle(12345, "THYAO", "100", "45.50")
    await m.portfoy_sil(12345, "THYAO")

    portfoy = await m.portfoy_getir(12345)
    assert len(portfoy) == 0
    
    await m.close_db()


@pytest.mark.asyncio
async def test_portfoy_decimal_hassasiyet(tmp_path):
    """Portföy Decimal hassasiyet testi."""
    db_file = str(tmp_path / "test.db")
    m = await _fresh_db(db_file)
    
    await m.kullanici_kaydet(12345, "testuser")
    # Hassas değer
    await m.portfoy_ekle(12345, "THYAO", "1000000", "0.00001")

    portfoy = await m.portfoy_getir(12345)
    assert len(portfoy) == 1
    # TEXT olarak saklandığı için hassasiyet korunmalı
    assert portfoy[0]['miktar'] == "1000000"
    assert portfoy[0]['maliyet'] == "0.00001"
    
    await m.close_db()
