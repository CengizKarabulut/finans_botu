"""
tests/test_edge_cases.py — Ek edge case testleri.
✅ YENİ - Güvenlik, performans ve kenar durum testleri.
"""
import os
import sys
import pytest
import time
from decimal import Decimal
from unittest.mock import AsyncMock, patch

os.environ["BOT_TOKEN"] = "1234567890:TEST_TOKEN"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.input_validator import validate_symbol, sanitize_text, validate_numeric
from security.rate_limiter import SlidingWindowRateLimiter
from security.circuit_breaker import CircuitBreaker
from veri_motoru import _parse_fiyat


# ═══════════════════════════════════════════════════════════════
# SEMBOL DOĞRULAMA EDGE CASE'LER
# ═══════════════════════════════════════════════════════════════

class TestValidateSymbolEdgeCases:
    """validate_symbol edge case testleri."""

    def test_6_harfli_bist_sembol(self):
        """6 harfli semboller BIST olarak tanınmalı (KCHOL gibi)."""
        valid, sembol, tip = validate_symbol("KCHOL")
        assert valid is True
        # 5 harfli -> BIST
        assert sembol == "KCHOL.IS"
        assert tip == "BIST"

    def test_googl_global_olarak_tanimlanmali(self):
        """GOOGL global sembol olarak tanınmalı, BIST olarak değil."""
        valid, sembol, tip = validate_symbol("GOOGL")
        assert valid is True
        assert tip == "GLOBAL"
        assert sembol == "GOOGL"

    def test_kripto_ayracsiz_usdt(self):
        """ETHUSDT kripto olarak tanınmalı."""
        valid, sembol, tip = validate_symbol("ETHUSDT")
        assert valid is True
        assert tip == "CRYPTO"
        assert "ETH" in sembol

    def test_kucuk_harf_sembol(self):
        """Küçük harfli giriş büyük harfe dönüşmeli."""
        valid, sembol, _ = validate_symbol("thyao")
        assert valid is True
        assert sembol == "THYAO.IS"

    def test_bosluklu_sembol(self):
        """Başta/sonda boşluklu girdi temizlenmeli."""
        valid, sembol, _ = validate_symbol("  AAPL  ")
        assert valid is True
        assert sembol == "AAPL"

    def test_cok_uzun_sembol(self):
        """Çok uzun sembol reddedilmeli."""
        valid, _, _ = validate_symbol("ABCDEFGHIJK")
        assert valid is False

    def test_sayisal_sembol(self):
        """Sadece sayı reddedilmeli."""
        valid, _, _ = validate_symbol("12345")
        assert valid is False

    def test_ozel_karakter_sembol(self):
        """Özel karakterli sembol reddedilmeli."""
        valid, _, _ = validate_symbol("THY@O")
        assert valid is False


# ═══════════════════════════════════════════════════════════════
# SANİTİZASYON GÜVENLİK TESTLERİ
# ═══════════════════════════════════════════════════════════════

class TestSanitizeTextSecurity:
    """sanitize_text güvenlik testleri."""

    def test_html_injection(self):
        """HTML injection engellenmeli."""
        result = sanitize_text("<script>alert('xss')</script>")
        assert "<" not in result
        assert ">" not in result
        assert "script" not in result.lower() or "alert" not in result

    def test_sql_injection_chars(self):
        """SQL injection karakterleri temizlenmeli."""
        result = sanitize_text("'; DROP TABLE users; --")
        assert "'" not in result
        assert ";" not in result or "DROP" not in result

    def test_unicode_injection(self):
        """Unicode injection engellenmeli."""
        result = sanitize_text("THY\u200BAO")  # zero-width space
        assert len(result) <= 10


# ═══════════════════════════════════════════════════════════════
# FİYAT PARSE EDGE CASE'LER
# ═══════════════════════════════════════════════════════════════

class TestParseFiyatEdgeCases:
    """_parse_fiyat edge case testleri."""

    def test_buyuk_turk_formati(self):
        """1.000.000,99 formatı doğru parse edilmeli."""
        result = _parse_fiyat("1.000.000,99")
        assert result is not None
        assert result == 1000000.99

    def test_negatif_fiyat(self):
        """Negatif fiyat (geçerli: vadeli işlemler)."""
        result = _parse_fiyat("-0.50")
        # Regex sadece sayısal karakterleri alır, eksi temizlenir
        assert result is not None

    def test_cok_kucuk_fiyat(self):
        """Çok küçük fiyat (kripto: SHIB)."""
        result = _parse_fiyat("0.00001234")
        assert result is not None
        assert abs(result - 0.00001234) < 1e-10

    def test_cok_buyuk_fiyat(self):
        """Çok büyük fiyat (BRK.A gibi)."""
        result = _parse_fiyat("625000.00")
        assert result == 625000.00

    def test_sadece_para_birimi(self):
        """Sadece para birimi sembolü verilirse None."""
        result = _parse_fiyat("USD")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# CIRCUIT BREAKER İLERİ TESTLERİ
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    """HALF_OPEN'dan CLOSED'a recovery testi."""
    cb = CircuitBreaker("test_recovery", failure_threshold=1, recovery_timeout=0)

    async def hatali():
        raise ValueError("test")

    async def basarili():
        return "OK"

    # OPEN'a geçir
    await cb.call(hatali)
    assert cb.state == "OPEN"

    # recovery_timeout=0 olduğu için hemen HALF_OPEN olmalı
    import asyncio
    await asyncio.sleep(0.01)

    # Başarılı çağrı → CLOSED'a dönmeli
    result = await cb.call(basarili)
    assert result == "OK"
    assert cb.state == "CLOSED"


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure():
    """HALF_OPEN'da tekrar hata → OPEN'a geri dönüş."""
    cb = CircuitBreaker("test_half_fail", failure_threshold=1, recovery_timeout=0)

    async def hatali():
        raise ValueError("test")

    # OPEN'a geçir
    await cb.call(hatali)
    assert cb.state == "OPEN"

    import asyncio
    await asyncio.sleep(0.01)

    # HALF_OPEN'da tekrar hata → OPEN
    await cb.call(hatali)
    assert cb.state == "OPEN"


# ═══════════════════════════════════════════════════════════════
# RATE LIMITER İLERİ TESTLERİ
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rate_limiter_window_expiry():
    """Window süresi dolunca yeniden izin verilmeli."""
    limiter = SlidingWindowRateLimiter(max_requests=1, window=1)
    user_id = 77777

    # İlk istek: izin ver
    allowed, _ = await limiter.check(user_id)
    assert allowed is True

    # Hemen tekrar: engelle
    allowed, wait_time = await limiter.check(user_id)
    assert allowed is False

    # 1 saniye bekle (window süresi)
    import asyncio
    await asyncio.sleep(1.1)

    # Şimdi tekrar izin vermeli
    allowed, _ = await limiter.check(user_id)
    assert allowed is True


@pytest.mark.asyncio
async def test_rate_limiter_different_users():
    """Farklı kullanıcılar bağımsız olmalı."""
    limiter = SlidingWindowRateLimiter(max_requests=1, window=60)

    allowed1, _ = await limiter.check(user_id=111)
    allowed2, _ = await limiter.check(user_id=222)

    assert allowed1 is True
    assert allowed2 is True


# ═══════════════════════════════════════════════════════════════
# NUMERIC DOĞRULAMA EDGE CASE'LER
# ═══════════════════════════════════════════════════════════════

class TestValidateNumericEdgeCases:
    """validate_numeric edge case testleri."""

    def test_sifir(self):
        result = validate_numeric("0", min_val=0)
        assert result == 0.0

    def test_cok_buyuk_sayi(self):
        result = validate_numeric("999999999.99")
        assert result is not None

    def test_bilimsel_notasyon(self):
        result = validate_numeric("1e5")
        assert result == 100000.0

    def test_bos_string(self):
        result = validate_numeric("")
        assert result is None

    def test_none_deger(self):
        result = validate_numeric(None)
        assert result is None
