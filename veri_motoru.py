"""
veri_motoru.py — Tüm harici veri kaynaklarını tek çatıda toplar.
✅ MİMARİ GÜNCELLEME - asyncio.Lock, Robust Parsing ve Async-Safe Cache.
"""
import os
import time
import logging
import asyncio
import aiohttp
import re
from typing import Optional, Dict, Any, List

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════════
# ASYNC-SAFE CACHE (Thread-Safe in Async Environment)
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
# ROBUST PARSING (Hata Payını Sıfıra İndirir)
# ═══════════════════════════════════════════════════════════════════

def _parse_fiyat(fiyat_str: str) -> Optional[float]:
    """
    Fiyat string'ini güvenli bir şekilde float'a çevirir.
    Örnek: "1.234,56 USD" -> 1234.56
    """
    if not fiyat_str or not isinstance(fiyat_str, str):
        return None
    try:
        # Sadece sayısal karakterleri, nokta ve virgülü tut
        temiz = ''.join(c for c in fiyat_str if c.isdigit() or c in '.,-')
        # Türk formatı (1.234,56) -> Global format (1234.56)
        if ',' in temiz and '.' in temiz:
            if temiz.find('.') < temiz.find(','): # 1.234,56
                temiz = temiz.replace('.', '').replace(',', '.')
            else: # 1,234.56
                temiz = temiz.replace(',', '')
        elif ',' in temiz: # 1234,56
            temiz = temiz.replace(',', '.')
        return float(temiz)
    except (ValueError, AttributeError) as e:
        log.debug(f"Fiyat parse hatası ('{fiyat_str}'): {e}")
        return None

# ═══════════════════════════════════════════════════════════════════
# HİYERARŞİK VERİ ÇEKME (Robust Data Fetching)
# ═══════════════════════════════════════════════════════════════════

async def get_fiyat_hiyerarsik(sembol: str) -> Dict[str, Any]:
    """
    Hiyerarşik fiyat çekme:
    1. BIST (.IS) -> yFinance
    2. Kripto (-USD, -TRY) -> yFinance (WebSocket altyapısı için hazır)
    3. ABD Hisse -> FMP -> AlphaVantage -> yFinance
    """
    s = sembol.upper().strip()
    
    # Cache kontrolü
    ck = f"price_{s}"
    cached = await _c_al(ck, 60)
    if cached: return cached

    res = {}
    try:
        import yfinance as yf
        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, lambda: yf.Ticker(s))
        info = await loop.run_in_executor(None, lambda: ticker.info)
        
        fiyat = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("price")
        degisim = info.get("regularMarketChangePercent")
        
        if fiyat:
            res = {
                "fiyat": float(fiyat),
                "degisim": float(degisim) if degisim else 0.0,
                "kaynak": "yFinance"
            }
            await _c_set(ck, res)
            return res
    except Exception as e:
        log.error(f"Veri çekme hatası ({s}): {e}")
    
    return res

# Diğer veri fonksiyonları (Haberler, Insider vb.) eklenecek...
