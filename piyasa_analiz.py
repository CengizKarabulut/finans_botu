"""
piyasa_analiz.py — Kripto, Döviz ve Emtia analiz modülü.

Teknik analiz için teknik_analiz.py'deki tam motoru kullanır:
  Supertrend, AlphaTrend, RSI Divergence, Stoch RSI, MACD, BB, ADX, CMF...
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
    # TRY bazlı
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
#  PİYASA BİLGİSİ (fiyat + genel metrikler)
# ─────────────────────────────────────────────────

def _piyasa_bilgisi(yf_sembol: str, goruntu: str, tip: str) -> dict:
    try:
        hisse = taze_ticker(yf_sembol)
        info  = hisse.info
        hist  = hisse.history(period="1y")

        if hist.empty:
            return {"Hata": f"{goruntu} icin veri bulunamadi."}

        c           = hist["Close"]
        son_fiyat   = c.iloc[-1]
        onceki      = c.iloc[-2] if len(c) > 1 else son_fiyat
        degisim_pct = (son_fiyat - onceki) / onceki * 100
        para_birimi = info.get("currency", "USD")

        s = {"_tip": tip, "_sembol": yf_sembol, "_goruntu": goruntu}

        if tip == "kripto":
            s["Isim"]            = info.get("name", goruntu)
            s["Para Birimi"]     = para_birimi
            s["Fiyat"]           = f"{son_fiyat:.6g} {para_birimi}"
            s["Degisim (%)"]     = f"{degisim_pct:+.2f}%"
            mkcap = info.get("marketCap", 0)
            if mkcap:
                s["Piyasa Degeri"] = f"{mkcap/1e9:.2f}B {para_birimi}" if mkcap < 1e12 else f"{mkcap/1e12:.2f}T {para_birimi}"
            vol = info.get("volume24Hr") or info.get("regularMarketVolume", 0)
            if vol:
                s["Hacim (24s)"] = f"{vol/1e6:.2f}M {para_birimi}"
            cs = info.get("circulatingSupply")
            if cs:
                s["Dolasim Arzi"] = f"{cs:,.0f}"
            ms = info.get("maxSupply")
            s["Maks Arz"] = f"{ms:,.0f}" if ms else "Sinırsız"

        elif tip == "doviz":
            s["Parite"]      = goruntu
            s["Aciklama"]    = info.get("shortName", goruntu)
            s["Fiyat"]       = f"{son_fiyat:.6g}"
            s["Degisim (%)"] = f"{degisim_pct:+.2f}%"
            for label, n in [("1 Hafta", 5), ("1 Ay", 21), ("3 Ay", 63), ("1 Yil", 252)]:
                if len(c) >= n:
                    g_pct = (c.iloc[-1] / c.iloc[-n] - 1) * 100
                    s[f"Getiri ({label})"] = f"{g_pct:+.2f}%"

        elif tip == "emtia":
            s["Aciklama"]    = info.get("shortName") or info.get("longName", goruntu)
            s["Para Birimi"] = para_birimi
            s["Borsa"]       = info.get("exchange", "-")
            s["Fiyat"]       = f"{son_fiyat:.6g} {para_birimi}"
            s["Degisim (%)"] = f"{degisim_pct:+.2f}%"
            for label, n in [("1 Hafta", 5), ("1 Ay", 21), ("3 Ay", 63), ("1 Yil", 252)]:
                if len(c) >= n:
                    g_pct = (c.iloc[-1] / c.iloc[-n] - 1) * 100
                    s[f"Getiri ({label})"] = f"{g_pct:+.2f}%"

        return s

    except Exception as e:
        return {"Hata": f"Veri cekilemedi: {e}"}


# ─────────────────────────────────────────────────
#  ANA ANALİZ FONKSİYONLARI
#  Döner: (piyasa_dict, teknik_dict)
#  teknik_dict → teknik_analiz.py'nin TAM çıktısı
#  (Supertrend, AlphaTrend, RSI Divergence, Stoch RSI, ADX, CMF...)
# ─────────────────────────────────────────────────

def kripto_analiz(sembol: str) -> tuple:
    yf_sembol, goruntu = sembol_coz(sembol, "kripto")
    piyasa = _piyasa_bilgisi(yf_sembol, goruntu, "kripto")
    if "Hata" in piyasa:
        return piyasa, {}
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
