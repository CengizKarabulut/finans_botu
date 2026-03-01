"""
piyasa_analiz.py — Kripto, Döviz ve Emtia analiz modülü.

Kripto: CoinGecko birincil (zengin veri) → yFinance fallback
Döviz/Emtia: yFinance (birincil, teknik analiz için gerekli)
"""

from cache_yonetici import taze_ticker
from teknik_analiz  import teknik_analiz_yap

# ─────────────────────────────────────────────────
#  SEMBOL HARİTALARI
# ─────────────────────────────────────────────────

KRIPTO_MAP = {
    "BTC":"BTC-USD","ETH":"ETH-USD","BNB":"BNB-USD","SOL":"SOL-USD",
    "XRP":"XRP-USD","ADA":"ADA-USD","AVAX":"AVAX-USD","DOT":"DOT-USD",
    "DOGE":"DOGE-USD","LINK":"LINK-USD","MATIC":"MATIC-USD","UNI":"UNI-USD",
    "LTC":"LTC-USD","ATOM":"ATOM-USD","NEAR":"NEAR-USD","APT":"APT-USD",
    "OP":"OP-USD","ARB":"ARB-USD","TON":"TON-USD","PEPE":"PEPE-USD",
    "SHIB":"SHIB-USD","TRX":"TRX-USD","SUI":"SUI-USD","INJ":"INJ-USD",
    "BTCTRY":"BTC-TRY","ETHTRY":"ETH-TRY","BNBTRY":"BNB-TRY",
    "SOLTRY":"SOL-TRY","XRPTRY":"XRP-TRY",
}

DOVIZ_MAP = {
    "USDTRY":"USDTRY=X","EURTRY":"EURTRY=X","GBPTRY":"GBPTRY=X",
    "JPYTRY":"JPYTRY=X","CHFTRY":"CHFTRY=X","CNYTRY":"CNYTRY=X",
    "RUBTRY":"RUBTRY=X","SARTRY":"SARTRY=X","AEDTRY":"AEDTRY=X",
    "EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X",
    "USDCHF":"USDCHF=X","AUDUSD":"AUDUSD=X","USDCAD":"USDCAD=X",
    "NZDUSD":"NZDUSD=X","EURGBP":"EURGBP=X","EURJPY":"EURJPY=X",
    "DOLAR":"USDTRY=X","EURO":"EURTRY=X","STERLIN":"GBPTRY=X",
    "YEN":"USDJPY=X","FRANK":"CHFTRY=X",
}

EMTIA_MAP = {
    "ALTIN":"GC=F","GUMUS":"SI=F","PLATIN":"PL=F","PALADYUM":"PA=F",
    "GOLD":"GC=F","SILVER":"SI=F",
    "PETROL":"CL=F","BRENT":"BZ=F","DOGALGAZ":"NG=F","GAZYAGI":"HO=F","BENZIN":"RB=F",
    "BAKIR":"HG=F","ALUMINYUM":"ALI=F","NIKEL":"NI=F","CINKO":"ZNC=F","DEMIR":"TIO=F",
    "MISIR":"ZC=F","BUGDAY":"ZW=F","SOYA":"ZS=F","KAHVE":"KC=F",
    "PAMUK":"CT=F","SEKER":"SB=F","KAKAO":"CC=F","PIRINC":"ZR=F",
    "SP500":"ES=F","NASDAQ":"NQ=F","DOW":"YM=F","DAX":"FDAX=F","NIKKEI":"NKD=F",
    "XU100":"XU100.IS","BIST100":"XU100.IS","BIST30":"XU030.IS",
}

KRIPTO_LISTE = ", ".join(sorted(KRIPTO_MAP.keys()))
DOVIZ_LISTE  = ", ".join(sorted(DOVIZ_MAP.keys()))
EMTIA_LISTE  = ", ".join(sorted(EMTIA_MAP.keys()))


# ─────────────────────────────────────────────────
#  SEMBOL ÇÖZÜMLEME
# ─────────────────────────────────────────────────

def sembol_coz(girdi: str, tip: str) -> tuple:
    g = girdi.upper().strip()
    if tip == "kripto":
        yf = KRIPTO_MAP.get(g, g if "-" in g else g + "-USD")
    elif tip == "doviz":
        yf = DOVIZ_MAP.get(g, g + "=X" if "=" not in g else g)
    elif tip == "emtia":
        yf = EMTIA_MAP.get(g, g)
    else:
        yf = g
    return yf, g


# ─────────────────────────────────────────────────
#  KRİPTO — CoinGecko önce, yFinance fallback
# ─────────────────────────────────────────────────

def _kripto_coingecko(yf_sembol: str, goruntu: str) -> dict:
    """CoinGecko'dan zengin kripto verisi çek."""
    try:
        from veri_motoru import coingecko_fiyat
        cg = coingecko_fiyat(yf_sembol)
        if cg:
            cg["_tip"]     = "kripto"
            cg["_sembol"]  = yf_sembol
            cg["_goruntu"] = goruntu
            cg["_kaynak"]  = "CoinGecko"
            return cg
    except Exception:
        pass
    return {}


def _kripto_yfinance(yf_sembol: str, goruntu: str) -> dict:
    """yFinance kripto verisi (fallback)."""
    try:
        hisse = taze_ticker(yf_sembol)
        info  = hisse.info
        hist  = hisse.history(period="1y")
        if hist.empty:
            return {"Hata": f"{goruntu} için veri bulunamadı."}

        c   = hist["Close"]
        son = c.iloc[-1]
        deg = (son - c.iloc[-2]) / c.iloc[-2] * 100 if len(c) > 1 else 0
        pb  = info.get("currency", "USD")

        s = {
            "_tip": "kripto", "_sembol": yf_sembol,
            "_goruntu": goruntu, "_kaynak": "yFinance",
            "Isim":          info.get("name", goruntu),
            "Para Birimi":   pb,
            "Fiyat":         f"{son:.6g} {pb}",
            "Degisim (%)":   f"{deg:+.2f}%",
        }
        mc = info.get("marketCap", 0)
        if mc:
            s["Piyasa Degeri"] = f"{mc/1e9:.2f}B {pb}" if mc < 1e12 else f"{mc/1e12:.2f}T {pb}"
        vol = info.get("volume24Hr") or info.get("regularMarketVolume", 0)
        if vol:
            s["Hacim (24s)"] = f"{vol/1e6:.2f}M {pb}"
        cs = info.get("circulatingSupply")
        if cs:
            s["Arz Dolaşım"] = f"{cs:,.0f}"
        return s
    except Exception as e:
        return {"Hata": f"Veri çekilemedi: {e}"}


# ─────────────────────────────────────────────────
#  DÖVİZ / EMTİA — yFinance
# ─────────────────────────────────────────────────

def _piyasa_bilgisi(yf_sembol: str, goruntu: str, tip: str) -> dict:
    try:
        hisse = taze_ticker(yf_sembol)
        info  = hisse.info
        hist  = hisse.history(period="1y")
        if hist.empty:
            return {"Hata": f"{goruntu} için veri bulunamadı."}

        c   = hist["Close"]
        son = c.iloc[-1]
        deg = (son - c.iloc[-2]) / c.iloc[-2] * 100 if len(c) > 1 else 0
        pb  = info.get("currency", "USD")

        s = {"_tip": tip, "_sembol": yf_sembol, "_goruntu": goruntu, "_kaynak": "yFinance"}

        if tip == "doviz":
            s["Parite"]      = goruntu
            s["Aciklama"]    = info.get("shortName", goruntu)
            s["Fiyat"]       = f"{son:.6g}"
            s["Degisim (%)"] = f"{deg:+.2f}%"
            for label, n in [("1 Hafta",5),("1 Ay",21),("3 Ay",63),("1 Yil",252)]:
                if len(c) >= n:
                    s[f"Getiri ({label})"] = f"{(c.iloc[-1]/c.iloc[-n]-1)*100:+.2f}%"

        elif tip == "emtia":
            s["Aciklama"]    = info.get("shortName") or info.get("longName", goruntu)
            s["Para Birimi"] = pb
            s["Borsa"]       = info.get("exchange", "-")
            s["Fiyat"]       = f"{son:.6g} {pb}"
            s["Degisim (%)"] = f"{deg:+.2f}%"
            for label, n in [("1 Hafta",5),("1 Ay",21),("3 Ay",63),("1 Yil",252)]:
                if len(c) >= n:
                    s[f"Getiri ({label})"] = f"{(c.iloc[-1]/c.iloc[-n]-1)*100:+.2f}%"

        return s
    except Exception as e:
        return {"Hata": f"Veri çekilemedi: {e}"}


# ─────────────────────────────────────────────────
#  ANA ANALİZ FONKSİYONLARI
# ─────────────────────────────────────────────────

def kripto_analiz(sembol: str) -> tuple:
    """CoinGecko → yFinance fallback. Teknik analiz yFinance'tan."""
    yf_sembol, goruntu = sembol_coz(sembol, "kripto")

    # Piyasa verisi: CoinGecko önce
    piyasa = _kripto_coingecko(yf_sembol, goruntu)
    if "Hata" in piyasa or not piyasa:
        piyasa = _kripto_yfinance(yf_sembol, goruntu)
    if "Hata" in piyasa:
        return piyasa, {}

    # Teknik analiz her zaman yFinance'tan (OHLCV gerektirir)
    teknik = teknik_analiz_yap(yf_sembol)
    return piyasa, teknik


def doviz_analiz(sembol: str) -> tuple:
    yf_sembol, goruntu = sembol_coz(sembol, "doviz")
    piyasa = _piyasa_bilgisi(yf_sembol, goruntu, "doviz")
    if "Hata" in piyasa:
        return piyasa, {}
    teknik = teknik_analiz_yap(yf_sembol)
    return piyasa, teknik


def emtia_analiz(sembol: str) -> tuple:
    yf_sembol, goruntu = sembol_coz(sembol, "emtia")
    piyasa = _piyasa_bilgisi(yf_sembol, goruntu, "emtia")
    if "Hata" in piyasa:
        return piyasa, {}
    teknik = teknik_analiz_yap(yf_sembol)
    return piyasa, teknik
