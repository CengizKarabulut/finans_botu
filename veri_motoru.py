"""
veri_motoru.py — Tüm harici veri kaynaklarını tek çatıda toplar.
✅ MİMARİ GÜNCELLEME - Circuit Breaker, Prometheus Metrics ve Robust Parsing.
"""
import os
import time
import logging
import asyncio
import aiohttp
import re
from typing import Optional, Dict, Any, List
from prometheus_client import Counter, Histogram

from config import settings
from security.circuit_breaker import cb_yfinance, cb_fmp, cb_alphavantage

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════════
# MONITORING (Prometheus Metrics)
# ═══════════════════════════════════════════════════════════════════
API_CALLS = Counter('api_calls_total', 'Toplam API çağrıları', ['provider', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('request_duration_seconds', 'İstek süresi', ['provider'])

# ═══════════════════════════════════════════════════════════════════
# ASYNC-SAFE CACHE
# ═══════════════════════════════════════════════════════════════════
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = asyncio.Lock()

async def _c_al(key: str, ttl: int = 300) -> Optional[Any]:
    async with _cache_lock:
        item = _cache.get(key)
        if item and (time.time() - item["ts"]) < ttl:
            return item["v"]
    return None

async def _c_set(key: str, val: Any) -> None:
    async with _cache_lock:
        _cache[key] = {"v": val, "ts": time.time()}

# ═══════════════════════════════════════════════════════════════════
# ROBUST PARSING
# ═══════════════════════════════════════════════════════════════════

def _parse_fiyat(fiyat_str: str) -> Optional[float]:
    if not fiyat_str or not isinstance(fiyat_str, str):
        return None
    try:
        temiz = ''.join(c for c in fiyat_str if c.isdigit() or c in '.,-')
        if ',' in temiz and '.' in temiz:
            if temiz.find('.') < temiz.find(','):
                temiz = temiz.replace('.', '').replace(',', '.')
            else:
                temiz = temiz.replace(',', '')
        elif ',' in temiz:
            temiz = temiz.replace(',', '.')
        return float(temiz)
    except (ValueError, AttributeError) as e:
        log.debug(f"Fiyat parse hatası ('{fiyat_str}'): {e}")
        return None

# ═══════════════════════════════════════════════════════════════════
# HİYERARŞİK VERİ ÇEKME (Robust & Resilient)
# ═══════════════════════════════════════════════════════════════════

async def get_fiyat_hiyerarsik(sembol: str) -> Dict[str, Any]:
    """
    Hiyerarşik fiyat çekme:
    ✅ MİMARİ İYİLEŞTİRME: Circuit Breaker ve Prometheus Metrics entegre edildi.
    """
    s = sembol.upper().strip()
    
    # Cache kontrolü (TTL config'den geliyor)
    ck = f"price_{s}"
    cached = await _c_al(ck, settings.CACHE_TTL_PRICE)
    if cached: return cached

    # 1. yFinance (Fallback & Primary for BIST/Crypto)
    res = await cb_yfinance.call(_fetch_yfinance, s)
    if res:
        await _c_set(ck, res)
        return res
    
    return {}

async def _fetch_yfinance(sembol: str) -> Optional[Dict[str, Any]]:
    """yFinance üzerinden veri çeker (Prometheus ile izlenir)."""
    start_time = time.time()
    try:
        import yfinance as yf
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, lambda: yf.Ticker(sembol))
        info = await loop.run_in_executor(None, lambda: ticker.info)
        
        fiyat = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("price")
        degisim = info.get("regularMarketChangePercent")
        
        if fiyat:
            API_CALLS.labels(provider='yfinance', endpoint='price', status='success').inc()
            return {
                "fiyat": float(fiyat),
                "degisim": float(degisim) if degisim else 0.0,
                "kaynak": "yFinance"
            }
    except Exception as e:
        API_CALLS.labels(provider='yfinance', endpoint='price', status='error').inc()
        log.error(f"yFinance hatası ({sembol}): {e}", exc_info=True)
        raise e # Circuit Breaker'ın hatayı görmesi için
    finally:
        REQUEST_DURATION.labels(provider='yfinance').observe(time.time() - start_time)
    
    return None
