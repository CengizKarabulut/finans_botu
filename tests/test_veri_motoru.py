"""
tests/test_veri_motoru.py — veri_motoru.py için unit testler.
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ["BOT_TOKEN"] = "1234567890:TEST_TOKEN"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from veri_motoru import _parse_fiyat


class TestParseFiyat:
    """_parse_fiyat fonksiyonu testleri."""

    def test_normal_sayi(self):
        result = _parse_fiyat("45.50")
        assert result == 45.50

    def test_turk_formati(self):
        """1.234,56 formatı (Türk)"""
        result = _parse_fiyat("1.234,56")
        assert result == 1234.56

    def test_global_formati(self):
        """1,234.56 formatı (Global)"""
        result = _parse_fiyat("1,234.56")
        assert result == 1234.56

    def test_sadece_virgul(self):
        """1234,56 formatı"""
        result = _parse_fiyat("1234,56")
        assert result == 1234.56

    def test_para_birimi_ile(self):
        """45.50 USD formatı"""
        result = _parse_fiyat("45.50 USD")
        assert result == 45.50

    def test_bos_string(self):
        result = _parse_fiyat("")
        assert result is None

    def test_none(self):
        result = _parse_fiyat(None)
        assert result is None

    def test_gecersiz_string(self):
        result = _parse_fiyat("abc")
        assert result is None

    def test_sifir(self):
        result = _parse_fiyat("0")
        assert result == 0.0

    def test_buyuk_sayi(self):
        result = _parse_fiyat("1.000.000,99")
        assert result is not None
