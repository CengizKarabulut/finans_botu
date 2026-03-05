"""
tests/test_alert_motoru.py — alert_motoru.py için unit testler.
"""
import os
import sys
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["BOT_TOKEN"] = "1234567890:TEST_TOKEN"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alert_motoru import _parse_decimal, _uyari_kontrol_et


class TestParseDecimal:
    """alert_motoru._parse_decimal fonksiyonu testleri."""

    def test_string_nokta(self):
        result = _parse_decimal("45.50")
        assert result == Decimal("45.50")

    def test_string_virgul(self):
        result = _parse_decimal("45,50")
        assert result == Decimal("45.50")

    def test_int(self):
        result = _parse_decimal(100)
        assert result == Decimal("100")

    def test_none(self):
        result = _parse_decimal(None)
        assert result is None

    def test_gecersiz(self):
        result = _parse_decimal("abc")
        assert result is None


@pytest.mark.asyncio
async def test_uyari_fiyat_ust_tetiklendi():
    """Fiyat üst uyarısı tetiklenme testi."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    uyari = {
        "id": 1,
        "user_id": 12345,
        "sembol": "THYAO",
        "tip": "fiyat_ust",
        "hedef_deger": "50.00"
    }

    with patch("alert_motoru.uyari_sil", new_callable=AsyncMock) as mock_sil:
        await _uyari_kontrol_et(
            mock_bot, uyari,
            mevcut_fiyat=Decimal("55.00"),
            mevcut_rsi=None
        )
        mock_bot.send_message.assert_called_once()
        mock_sil.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_uyari_fiyat_ust_tetiklenmedi():
    """Fiyat üst uyarısı tetiklenmeme testi (fiyat düşük)."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    uyari = {
        "id": 1,
        "user_id": 12345,
        "sembol": "THYAO",
        "tip": "fiyat_ust",
        "hedef_deger": "50.00"
    }

    with patch("alert_motoru.uyari_sil", new_callable=AsyncMock) as mock_sil:
        await _uyari_kontrol_et(
            mock_bot, uyari,
            mevcut_fiyat=Decimal("45.00"),
            mevcut_rsi=None
        )
        mock_bot.send_message.assert_not_called()
        mock_sil.assert_not_called()


@pytest.mark.asyncio
async def test_uyari_fiyat_alt_tetiklendi():
    """Fiyat alt uyarısı tetiklenme testi."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    uyari = {
        "id": 2,
        "user_id": 12345,
        "sembol": "THYAO",
        "tip": "fiyat_alt",
        "hedef_deger": "40.00"
    }

    with patch("alert_motoru.uyari_sil", new_callable=AsyncMock) as mock_sil:
        await _uyari_kontrol_et(
            mock_bot, uyari,
            mevcut_fiyat=Decimal("35.00"),
            mevcut_rsi=None
        )
        mock_bot.send_message.assert_called_once()
        mock_sil.assert_called_once_with(2)


@pytest.mark.asyncio
async def test_uyari_rsi_ust_tetiklendi():
    """RSI üst uyarısı tetiklenme testi."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    uyari = {
        "id": 3,
        "user_id": 12345,
        "sembol": "THYAO",
        "tip": "rsi_ust",
        "hedef_deger": "70"
    }

    with patch("alert_motoru.uyari_sil", new_callable=AsyncMock) as mock_sil:
        await _uyari_kontrol_et(
            mock_bot, uyari,
            mevcut_fiyat=Decimal("50.00"),
            mevcut_rsi=Decimal("75.00")
        )
        mock_bot.send_message.assert_called_once()
        mock_sil.assert_called_once_with(3)


@pytest.mark.asyncio
async def test_uyari_rsi_alt_tetiklendi():
    """RSI alt uyarısı tetiklenme testi."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    uyari = {
        "id": 4,
        "user_id": 12345,
        "sembol": "THYAO",
        "tip": "rsi_alt",
        "hedef_deger": "30"
    }

    with patch("alert_motoru.uyari_sil", new_callable=AsyncMock) as mock_sil:
        await _uyari_kontrol_et(
            mock_bot, uyari,
            mevcut_fiyat=Decimal("50.00"),
            mevcut_rsi=Decimal("25.00")
        )
        mock_bot.send_message.assert_called_once()
        mock_sil.assert_called_once_with(4)


@pytest.mark.asyncio
async def test_uyari_hedef_none():
    """Hedef değer None ise uyarı tetiklenmemeli."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    uyari = {
        "id": 5,
        "user_id": 12345,
        "sembol": "THYAO",
        "tip": "fiyat_ust",
        "hedef_deger": None
    }

    with patch("alert_motoru.uyari_sil", new_callable=AsyncMock) as mock_sil:
        await _uyari_kontrol_et(
            mock_bot, uyari,
            mevcut_fiyat=Decimal("50.00"),
            mevcut_rsi=None
        )
        mock_bot.send_message.assert_not_called()
        mock_sil.assert_not_called()
