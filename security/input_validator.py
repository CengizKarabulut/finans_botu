"""
security/input_validator.py — Kullanıcı girdilerini denetler.
✅ MİMARİ GÜNCELLEME - Zeki sembol doğrulama ve sanitizasyon.
"""
import re
import logging
from typing import Optional, List

log = logging.getLogger("finans_botu")

def validate_symbol(symbol: str) -> bool:
    """
    Sembolün geçerli bir formatta olup olmadığını kontrol eder.
    Geçerli formatlar:
    - THYAO, THYAO.IS (BIST)
    - BTCUSD, BTC-USD, BTC-TRY (Kripto)
    - AAPL, MSFT (Global)
    - USDTRY, EURUSD (Döviz)
    """
    if not symbol or not isinstance(symbol, str):
        return False
    
    # 1. Uzunluk kontrolü (Min 2, Max 15)
    if not (2 <= len(symbol) <= 15):
        return False
    
    # 2. Karakter kontrolü (Harf, rakam, nokta, tire, eşittir)
    # Regex: Sadece izin verilen karakterler
    if not re.match(r'^[A-Z0-9.\-=]+$', symbol.upper()):
        log.warning(f"Geçersiz karakter içeren sembol reddedildi: {symbol}")
        return False
    
    # 3. Özel durumlar (Sadece nokta veya sadece tire olamaz)
    if symbol.strip(".-=") == "":
        return False
        
    return True

def sanitize_text(text: str, max_length: int = 1000) -> str:
    """
    Kullanıcı girdisini sanitize et (XSS prevention).
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Length limit
    text = text[:max_length]
    
    # Sadece harf, rakam ve temel finansal karakterleri bırak
    clean = re.sub(r'[^\w\s.\-=]', '', text)
    return clean.strip().upper()

def validate_numeric(value: str, min_val: float = None, max_val: float = None) -> Optional[float]:
    """
    String değeri numeric'e çevir ve range kontrolü yap.
    """
    try:
        # Virgülü noktaya çevir (TR formatı desteği)
        num = float(value.replace(',', '.'))
        if min_val is not None and num < min_val:
            return None
        if max_val is not None and num > max_val:
            return None
        return num
    except (ValueError, TypeError):
        return None

def validate_command_args(args: List[str], expected_count: int) -> bool:
    """Komut argüman sayısını kontrol et."""
    return len(args) == expected_count
