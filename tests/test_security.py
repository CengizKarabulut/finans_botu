"""
tests/test_security.py — security modülleri için unit testler.
"""
import os
import sys
import pytest
import asyncio

os.environ["BOT_TOKEN"] = "1234567890:TEST_TOKEN"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.input_validator import validate_symbol, sanitize_text, validate_numeric
from security.rate_limiter import SlidingWindowRateLimiter
from security.circuit_breaker import CircuitBreaker


# ═══════════════════════════════════════════════════════════════
# INPUT VALIDATOR TESTLERİ
# ═══════════════════════════════════════════════════════════════

class TestValidateSymbol:
    def test_bist_sembol(self):
        valid, sembol, tip = validate_symbol("THYAO")
        assert valid is True
        assert sembol == "THYAO.IS"
        assert tip == "BIST"

    def test_bist_sembol_with_is(self):
        valid, sembol, tip = validate_symbol("THYAO.IS")
        assert valid is True
        assert sembol == "THYAO.IS"
        assert tip == "BIST"

    def test_global_sembol(self):
        valid, sembol, tip = validate_symbol("AAPL")
        assert valid is True
        assert sembol == "AAPL"
        assert tip == "GLOBAL"

    def test_kripto_sembol_dash(self):
        valid, sembol, tip = validate_symbol("BTC-USD")
        assert valid is True
        assert tip == "CRYPTO"

    def test_kripto_sembol_no_separator(self):
        valid, sembol, tip = validate_symbol("BTCUSD")
        assert valid is True
        assert tip == "CRYPTO"

    def test_gecersiz_sembol(self):
        valid, sembol, tip = validate_symbol("INVALID_SYMBOL_123456")
        assert valid is False

    def test_bos_sembol(self):
        valid, sembol, tip = validate_symbol("")
        assert valid is False

    def test_none_sembol(self):
        valid, sembol, tip = validate_symbol(None)
        assert valid is False

    def test_kucuk_harf(self):
        valid, sembol, tip = validate_symbol("thyao")
        assert valid is True
        assert sembol == "THYAO.IS"


class TestSanitizeText:
    def test_normal_metin(self):
        result = sanitize_text("THYAO")
        assert result == "THYAO"

    def test_ozel_karakterler(self):
        result = sanitize_text("THYAO<script>alert('xss')</script>")
        assert "<" not in result
        assert ">" not in result

    def test_max_uzunluk(self):
        uzun_metin = "A" * 2000
        result = sanitize_text(uzun_metin, max_length=100)
        assert len(result) <= 100

    def test_bos_metin(self):
        result = sanitize_text("")
        assert result == ""


class TestValidateNumeric:
    def test_gecerli_sayi(self):
        result = validate_numeric("45.50")
        assert result == 45.50

    def test_virgul_format(self):
        result = validate_numeric("45,50")
        assert result == 45.50

    def test_min_kontrol(self):
        result = validate_numeric("-5", min_val=0)
        assert result is None

    def test_max_kontrol(self):
        result = validate_numeric("1000", max_val=100)
        assert result is None

    def test_gecersiz_deger(self):
        result = validate_numeric("abc")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# RATE LIMITER TESTLERİ
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rate_limiter_izin():
    """Rate limiter normal istek testi."""
    limiter = SlidingWindowRateLimiter(max_requests=5, window=60)
    allowed, wait_time = await limiter.check(user_id=99999)
    assert allowed is True
    assert wait_time == 0


@pytest.mark.asyncio
async def test_rate_limiter_engel():
    """Rate limiter limit aşımı testi."""
    limiter = SlidingWindowRateLimiter(max_requests=3, window=60)
    user_id = 88888

    # 3 istek gönder (limit)
    for _ in range(3):
        allowed, _ = await limiter.check(user_id)
        assert allowed is True

    # 4. istek engellenmiş olmalı
    allowed, wait_time = await limiter.check(user_id)
    assert allowed is False
    assert wait_time > 0


# ═══════════════════════════════════════════════════════════════
# CIRCUIT BREAKER TESTLERİ
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_circuit_breaker_closed():
    """Circuit Breaker normal durum testi."""
    cb = CircuitBreaker("test_cb", failure_threshold=3, recovery_timeout=60)
    assert cb.state == "CLOSED"

    async def basarili_func():
        return "OK"

    result = await cb.call(basarili_func)
    assert result == "OK"
    assert cb.state == "CLOSED"
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_circuit_breaker_open():
    """Circuit Breaker açılma testi."""
    cb = CircuitBreaker("test_cb_open", failure_threshold=2, recovery_timeout=60)

    async def hatali_func():
        raise ValueError("Test hatası")

    # 2 hata → OPEN
    for _ in range(2):
        await cb.call(hatali_func)

    assert cb.state == "OPEN"


@pytest.mark.asyncio
async def test_circuit_breaker_open_rejects():
    """Circuit Breaker açıkken istek reddetme testi."""
    cb = CircuitBreaker("test_cb_reject", failure_threshold=1, recovery_timeout=3600)

    async def hatali_func():
        raise ValueError("Test hatası")

    await cb.call(hatali_func)
    assert cb.state == "OPEN"

    # OPEN durumda None döndürmeli
    result = await cb.call(hatali_func)
    assert result is None
