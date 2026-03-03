"""Input validation and sanitization helpers."""
import re
import logging
from typing import Optional, List

log = logging.getLogger("finans_botu")

# Güvenli sembol pattern'i (sadece harf, sayı, nokta, tire)
SYMBOL_PATTERN = re.compile(r'^[A-Z0-9.\-]{1,20}$', re.IGNORECASE)

# Güvenli mesaj pattern'i (XSS önleme)
UNSAFE_CHARS = re.compile(r'[<>"\';\\]')

def validate_symbol(symbol: str, allow_extensions: bool = True) -> Optional[str]:
    """
    Sembolü validate et ve normalize et.
    
    Returns:
        Normalized symbol veya None (geçersiz ise)
    """
    if not symbol or not isinstance(symbol, str):
        return None
    
    # Trim ve uppercase
    symbol = symbol.strip().upper()
    
    # Bilinen borsaları koru
    if allow_extensions:
        known_extensions = {'.IS', '.L', '.DE', '.PA', '.MI', '.AS', '.HK', '.T'}
        for ext in known_extensions:
            if symbol.endswith(ext):
                base = symbol[:-len(ext)]
                if SYMBOL_PATTERN.match(base):
                    return symbol
    
    # Base sembol kontrolü
    if SYMBOL_PATTERN.match(symbol):
        return symbol
    
    log.warning(f"Invalid symbol rejected: {symbol}")
    return None

def sanitize_text(text: str, max_length: int = 1000) -> str:
    """
    Kullanıcı girdisini sanitize et (XSS prevention).
    
    Returns:
        Temizlenmiş metin
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Length limit
    text = text[:max_length]
    
    # Unsafe karakterleri escape et
    replacements = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        ';': '&#x3B;',
        '\\': '&#x5C;',
    }
    
    for unsafe, safe in replacements.items():
        text = text.replace(unsafe, safe)
    
    return text.strip()

def validate_numeric(value: str, min_val: float = None, max_val: float = None) -> Optional[float]:
    """
    String değeri numeric'e çevir ve range kontrolü yap.
    
    Returns:
        float değer veya None (geçersiz ise)
    """
    try:
        num = float(value)
        if min_val is not None and num < min_val:
            return None
        if max_val is not None and num > max_val:
            return None
        return num
    except (ValueError, TypeError):
        return None

def validate_command_args(args: List[str], expected_count: int, 
                         validators: List[callable] = None) -> bool:
    """
    Komut argümanlarını validate et.
    
    Args:
        args: Argüman listesi
        expected_count: Beklenen argüman sayısı
        validators: Her argüman için validation fonksiyonları (opsiyonel)
    
    Returns:
        True if valid, False otherwise
    """
    if len(args) != expected_count:
        return False
    
    if validators:
        for i, (arg, validator) in enumerate(zip(args, validators)):
            if validator and not validator(arg):
                log.warning(f"Arg {i} validation failed: {arg}")
                return False
    
    return True
