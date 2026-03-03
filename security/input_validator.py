"""Input validation — XSS ve invalid input önleme."""
import re
import logging

log = logging.getLogger("finans_botu")

SYMBOL_PATTERN = re.compile(r'^[A-Z0-9.\-]{1,20}$', re.IGNORECASE)

def validate_symbol(symbol: str) -> str:
    """Sembolü validate et ve normalize et."""
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Geçersiz sembol")
    
    symbol = symbol.strip().upper()
    
    known_ext = {'.IS', '.L', '.DE', '.PA', '.MI', '.AS', '.HK', '.T'}
    for ext in known_ext:
        if symbol.endswith(ext):
            base = symbol[:-len(ext)]
            if SYMBOL_PATTERN.match(base):
                return symbol
    
    if SYMBOL_PATTERN.match(symbol):
        return symbol
    
    raise ValueError(f"Geçersiz sembol formatı: {symbol}")

def sanitize_text(text: str, max_length: int = 1000) -> str:
    """Kullanıcı girdisini temizle (XSS prevention)."""
    if not text:
        return ""
    text = text[:max_length]
    replacements = {'<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;'}
    for unsafe, safe in replacements.items():
        text = text.replace(unsafe, safe)
    return text.strip()
