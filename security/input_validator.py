"""
security/input_validator.py — Kullanıcı girdilerini denetler.
✅ MİMARİ GÜNCELLEME - Zeki sembol doğrulama ve sanitizasyon.
✅ DÜZELTİLDİ - Kripto regex boşluk hatası ve BIST/GLOBAL ayrımı düzeltildi.

Sembol Tipi Belirleme Mantığı:
  1. Kripto: BASE-QUOTE veya BASEQUOTE formatı (BTC-USD, BTCUSD)
  2. BIST: .IS uzantısı varsa kesinlikle BIST
  3. GLOBAL: Bilinen global hisse borsası öneki varsa (AAPL, MSFT, TSLA vb.)
  4. BIST: 4-5 harfli Türkçe hisse kodu formatı (THYAO, ASELS)
  5. GLOBAL: 1-3 harfli semboller (GE, IBM vb.)
"""
import re
import logging
from typing import Optional, List, Tuple

log = logging.getLogger("finans_botu")

# Bilinen global borsalardaki popüler semboller (BIST ile çakışmayanlar)
# 4 harfli semboller için çakışma önleme listesi
_BILINEN_GLOBAL_SEMBOLLER = {
    # ABD Hisseleri
    "AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA", "NVDA", "NFLX",
    "BABA", "INTC", "CSCO", "ORCL", "ADBE", "PYPL", "UBER", "LYFT",
    "SNAP", "TWTR", "SPOT", "SHOP", "ZOOM", "COIN", "HOOD", "RBLX",
    "PLTR", "SOFI", "LCID", "RIVN", "DKNG", "PENN", "WYNN", "MGM",
    "MRNA", "BNTX", "PFE", "JNJ", "ABBV", "LLY", "BMY", "AMGN",
    "GILD", "BIIB", "REGN", "VRTX", "ILMN", "IDXX", "DXCM", "ALGN",
    "ISRG", "SYK", "MDT", "ABT", "BSX", "EW", "ZBH", "HOLX",
    "JPM", "BAC", "WFC", "GS", "MS", "C", "USB", "PNC",
    "V", "MA", "AXP", "DIS", "KO", "PEP", "MCD", "SBUX",
    "NKE", "LULU", "TGT", "WMT", "COST", "HD", "LOW", "TJX",
    "XOM", "CVX", "COP", "SLB", "HAL", "OXY", "MPC", "PSX",
    "BA", "LMT", "RTX", "NOC", "GD", "HII", "TDG", "HEI",
    "GOOGL", "GOOG",
    # Avrupa Hisseleri
    "ASML", "SAP", "LVMH", "NESN", "NOVN", "RHHBY",
    # Japon Hisseleri
    "SONY", "TM", "HMC",
}

# Kripto para birimleri
_KRIPTO_QUOTE_CURRENCIES = {"USD", "USDT", "TRY", "EUR", "BTC", "ETH", "BNB", "USDC"}
_KRIPTO_BASE_CURRENCIES = {
    "BTC", "ETH", "BNB", "SOL", "ADA", "XRP", "DOT", "AVAX", "MATIC",
    "LINK", "UNI", "ATOM", "LTC", "DOGE", "SHIB", "TRX", "XLM", "ALGO",
    "VET", "FIL", "THETA", "XTZ", "EOS", "AAVE", "COMP", "MKR", "SNX",
    "YFI", "SUSHI", "CRV", "BAL", "ZRX", "KNC", "LRC", "REN", "NMR",
    "NEAR", "FTM", "ONE", "HBAR", "EGLD", "SAND", "MANA", "AXS", "ENJ",
    "CHZ", "GALA", "IMX", "APE", "GMT", "STX", "FLOW", "ICP", "HNT",
    "KLAY", "ROSE", "CELO", "ZIL", "QTUM", "ICX", "ONT", "ZEN", "DCR",
    "DASH", "ZEC", "XMR", "ETC", "BCH", "BSV",
}


def validate_symbol(symbol: str) -> Tuple[bool, str, str]:
    """
    Sembolü doğrular ve tipini belirler.
    Dönüş: (Geçerli mi?, Normalize Sembol, Tip)
    Tipler: 'BIST', 'CRYPTO', 'GLOBAL', 'UNKNOWN'
    """
    if not symbol or not isinstance(symbol, str):
        return False, "", "UNKNOWN"

    s = symbol.upper().strip()

    # 1. BIST uzantısı varsa kesinlikle BIST
    if s.endswith(".IS"):
        base = s[:-3]
        if re.match(r'^[A-Z]{2,6}$', base):
            return True, s, "BIST"
        return False, s, "UNKNOWN"

    # 2. Kripto Kontrolü — ayraçlı format (BTC-USD, ETH/USDT)
    kripto_ayracli = r'^([A-Z0-9]{2,10})[-/]([A-Z0-9]{2,10})$'
    m = re.match(kripto_ayracli, s)
    if m:
        base, quote = m.group(1), m.group(2)
        if quote in _KRIPTO_QUOTE_CURRENCIES:
            return True, f"{base}-{quote}", "CRYPTO"

    # 3. Kripto Kontrolü — ayraçsız format (BTCUSD, ETHUSDT)
    for quote in sorted(_KRIPTO_QUOTE_CURRENCIES, key=len, reverse=True):
        if s.endswith(quote) and len(s) > len(quote):
            base = s[:-len(quote)]
            if len(base) >= 2 and re.match(r'^[A-Z0-9]+$', base):
                return True, f"{base}-{quote}", "CRYPTO"

    # 4. Bilinen global semboller listesinde mi?
    if s in _BILINEN_GLOBAL_SEMBOLLER:
        return True, s, "GLOBAL"

    # 5. BIST formatı: 4-5 büyük harf (THYAO, ASELS, SASA, KCHOL vb.)
    if re.match(r'^[A-Z]{4,5}$', s):
        return True, f"{s}.IS", "BIST"

    # 6. Global format: 1-3 büyük harf (GE, IBM, F, GM vb.)
    if re.match(r'^[A-Z]{1,3}$', s):
        return True, s, "GLOBAL"

    # 7. Uzun global semboller (GOOGL, GOOG gibi 5+ harf ama BIST değil)
    if re.match(r'^[A-Z]{5,6}$', s):
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

    # HTML özel karakterlerini temizle
    clean = re.sub(r'[<>&"\']', '', text)
    # Sadece alfanümerik, boşluk ve temel finansal karakterleri bırak
    clean = re.sub(r'[^\w\s.\-=/]', '', clean)
    return clean.strip().upper()


def validate_numeric(value: str, min_val: float = None, max_val: float = None) -> Optional[float]:
    """
    String değeri numeric'e çevir ve range kontrolü yap.
    """
    try:
        # Virgülü noktaya çevir (TR formatı desteği)
        num = float(str(value).replace(',', '.'))
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
