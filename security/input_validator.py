"""
security/input_validator.py — Kullanıcı girdilerini denetler.
✅ MİMARİ GÜNCELLEME - Zeki sembol doğrulama ve sanitizasyon.
"""
import re
import logging
from typing import Optional, List, Tuple

log = logging.getLogger("finans_botu")

def validate_symbol(symbol: str) -> Tuple[bool, str, str]:
    """
    Sembolü doğrular ve tipini belirler.
    Dönüş: (Geçerli mi?, Normalize Sembol, Tip)
    Tipler: 'BIST', 'CRYPTO', 'GLOBAL', 'UNKNOWN'
    """
    if not symbol or not isinstance(symbol, str):
        return False, "", "UNKNOWN"
    
    s = symbol.upper().strip()
    
    # 1. Kripto Kontrolü (BTCUSD, BTC-USDT, ETH/TRY vb.)
    kripto_regex = r'^([A-Z0-9]{2,10})[-/]? (USD|USDT|TRY|EUR|BTC|ETH)$'
    kripto_match = re.match(kripto_regex, s)
    if kripto_match:
        base, quote = kripto_match.groups()
        return True, f"{base}-{quote}", "CRYPTO"
    
    # 2. BIST Kontrolü (THYAO, ASELS.IS vb.)
    bist_regex = r'^([A-Z]{4,5})(\.IS)?$'
    bist_match = re.match(bist_regex, s)
    if bist_match:
        base = bist_match.group(1)
        return True, f"{base}.IS", "BIST"
    
    # 3. Global Kontrol (AAPL, TSLA, MSFT vb.)
    global_regex = r'^([A-Z]{1,5})$'
    global_match = re.match(global_regex, s)
    if global_match:
        return True, s, "GLOBAL"
        
    return False, s, "UNKNOWN"

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
