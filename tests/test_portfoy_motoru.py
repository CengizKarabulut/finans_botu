"""
tests/test_portfoy_motoru.py — portfoy_motoru.py için unit testler.
"""
import os
import sys
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

os.environ["BOT_TOKEN"] = "1234567890:TEST_TOKEN"
os.environ["DB_PATH"] = "/tmp/test_portfoy_motoru.db"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfoy_motoru import _parse_decimal, portfoy_varlik_ekle


class TestParseDecimal:
    """_parse_decimal fonksiyonu testleri."""

    def test_string_nokta(self):
        result = _parse_decimal("45.50")
        assert result == Decimal("45.50")

    def test_string_virgul(self):
        result = _parse_decimal("45,50")
        assert result == Decimal("45.50")

    def test_int(self):
        result = _parse_decimal(100)
        assert result == Decimal("100")

    def test_float(self):
        result = _parse_decimal(45.5)
        assert result is not None

    def test_none(self):
        result = _parse_decimal(None)
        assert result is None

    def test_gecersiz_string(self):
        result = _parse_decimal("abc")
        assert result is None

    def test_bos_string(self):
        result = _parse_decimal("")
        assert result is None

    def test_buyuk_sayi(self):
        result = _parse_decimal("1000000.99")
        assert result == Decimal("1000000.99")


@pytest.mark.asyncio
async def test_portfoy_varlik_ekle_gecersiz_miktar():
    """Geçersiz miktar ile portföy ekleme testi."""
    sonuc = await portfoy_varlik_ekle(12345, "THYAO", "-10", "45.50")
    assert "❌" in sonuc


@pytest.mark.asyncio
async def test_portfoy_varlik_ekle_gecersiz_maliyet():
    """Geçersiz maliyet ile portföy ekleme testi."""
    sonuc = await portfoy_varlik_ekle(12345, "THYAO", "100", "abc")
    assert "❌" in sonuc


@pytest.mark.asyncio
async def test_portfoy_varlik_ekle_basarili():
    """Başarılı portföy ekleme testi."""
    from db import db_init, close_db

    db_path = "/tmp/test_portfoy_motoru.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    await db_init()

    from db import kullanici_kaydet
    await kullanici_kaydet(12345, "testuser")

    sonuc = await portfoy_varlik_ekle(12345, "THYAO", "100", "45.50")
    assert "✅" in sonuc
    assert "THYAO" in sonuc

    await close_db()
    if os.path.exists(db_path):
        os.remove(db_path)
