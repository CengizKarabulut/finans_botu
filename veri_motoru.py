"""
veri_motoru.py — Tüm harici veri kaynaklarını tek çatıda toplar.

Hiyerarşi (her kaynak bir öncekinin fallback'i):
  KAP/BIST  : borsapy (birincil) → yFinance (fallback)
  ABD Hisse : SEC EDGAR (birincil) → FMP (fallback) → yFinance (fallback)
  Kripto    : CoinGecko (birincil) → yFinance (fallback)
  Haber     : Finnhub → yFinance news → borsapy news (BIST için)
  Insider   : Finnhub → yFinance insider_transactions
  Sembol    : OpenFIGI (çözümleme) → yFinance

Tüm key'ler ortam değişkeninden:
  FINNHUB_API_KEY, COINGECKO_API_KEY, FMP_API_KEY,
  ALPHAVANTAGE_API_KEY, OPENFIGI_API_KEY
"""

import os
import time
import requests
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
#  ORTAK CACHE
# ─────────────────────────────────────────────

_cache: dict = {}

def _c_al(key: str, ttl: int = 300):
    item = _cache.get(key)
    if item and (time.time() - item["ts"]) < ttl:
        return item["v"]
    return None

def _c_set(key: str, val):
    _cache[key] = {"v": val, "ts": time.time()}

def _key(name: str) -> str:
    return os.environ.get(name, "")

# ─────────────────────────────────────────────
#  YARDIMCI: HTTP GET
# ─────────────────────────────────────────────

def _get(url: str, params: dict = None, headers: dict = None, timeout: int = 10) -> dict | list | None:
    try:
        r = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None

def _post(url: str, body: list, headers: dict = None, timeout: int = 10) -> list | None:
    try:
        r = requests.post(url, json=body, headers=headers or {}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════════
#  1. OPENFIGI — Sembol Çözümleme (Ücretsiz, Sınırsız)
# ═══════════════════════════════════════════════════════════════════

def openfigi_sembol(ticker: str, exchange: str = "US") -> dict:
    """
    Bloomberg OpenFIGI ile ticker → şirket adı, borsa, para birimi, FIGI.
    exchange kodları: US, LN, GR, FP, HK, AT (Türkiye için), AX, TT...
    """
    ck = f"figi_{ticker}_{exchange}"
    cached = _c_al(ck, ttl=3600)  # 1 saat cache
    if cached is not None:
        return cached

    headers = {"Content-Type": "application/json"}
    figi_key = _key("OPENFIGI_API_KEY")
    if figi_key:
        headers["X-OPENFIGI-APIKEY"] = figi_key

    body = [{"idType": "TICKER", "idValue": ticker, "exchCode": exchange}]
    sonuc_raw = _post("https://api.openfigi.com/v3/mapping", body, headers)

    sonuc = {}
    if sonuc_raw and sonuc_raw[0].get("data"):
        ilk = sonuc_raw[0]["data"][0]
        sonuc = {
            "ad":          ilk.get("name", ""),
            "borsa":       ilk.get("exchCode", ""),
            "tip":         ilk.get("securityType", ""),
            "para_birimi": ilk.get("currency", ""),
            "figi":        ilk.get("figi", ""),
        }

    _c_set(ck, sonuc)
    return sonuc


def openfigi_isin(isin: str) -> dict:
    """ISIN → ticker ve borsa bilgisi."""
    ck = f"figi_isin_{isin}"
    cached = _c_al(ck, ttl=3600)
    if cached is not None:
        return cached

    headers = {"Content-Type": "application/json"}
    figi_key = _key("OPENFIGI_API_KEY")
    if figi_key:
        headers["X-OPENFIGI-APIKEY"] = figi_key

    body = [{"idType": "ID_ISIN", "idValue": isin}]
    sonuc_raw = _post("https://api.openfigi.com/v3/mapping", body, headers)

    sonuc = {}
    if sonuc_raw and sonuc_raw[0].get("data"):
        ilk = sonuc_raw[0]["data"][0]
        sonuc = {
            "ticker":      ilk.get("ticker", ""),
            "ad":          ilk.get("name", ""),
            "borsa":       ilk.get("exchCode", ""),
            "para_birimi": ilk.get("currency", ""),
        }

    _c_set(ck, sonuc)
    return sonuc


# ═══════════════════════════════════════════════════════════════════
#  2. COINGECKO — Kripto (10.000 istek/ay ücretsiz)
# ═══════════════════════════════════════════════════════════════════

# yFinance sembol → CoinGecko ID eşleştirmesi
_CG_ID_MAP = {
    "BTC-USD": "bitcoin",    "ETH-USD": "ethereum",
    "BNB-USD": "binancecoin","SOL-USD": "solana",
    "XRP-USD": "ripple",     "ADA-USD": "cardano",
    "AVAX-USD":"avalanche-2","DOT-USD": "polkadot",
    "DOGE-USD":"dogecoin",   "LINK-USD":"chainlink",
    "MATIC-USD":"matic-network","UNI-USD":"uniswap",
    "LTC-USD": "litecoin",   "ATOM-USD":"cosmos",
    "NEAR-USD":"near",       "APT-USD": "aptos",
    "OP-USD":  "optimism",   "ARB-USD": "arbitrum",
    "TON-USD": "the-open-network","PEPE-USD":"pepe",
    "SHIB-USD":"shiba-inu",  "TRX-USD": "tron",
    "SUI-USD": "sui",        "INJ-USD": "injective-protocol",
    "BTC-TRY": "bitcoin",    "ETH-TRY": "ethereum",
    "BNB-TRY": "binancecoin","SOL-TRY": "solana",
    "XRP-TRY": "ripple",
}

def _cg_headers() -> dict:
    h = {"accept": "application/json"}
    k = _key("COINGECKO_API_KEY")
    if k:
        h["x-cg-demo-api-key"] = k
    return h

def _cg_base() -> str:
    return "https://api.coingecko.com/api/v3"


def coingecko_fiyat(yf_sembol: str) -> dict:
    """
    CoinGecko'dan kripto fiyatı + piyasa verileri.
    yf_sembol: BTC-USD, ETH-TRY vb.
    """
    cg_id = _CG_ID_MAP.get(yf_sembol.upper())
    if not cg_id:
        return {}

    para_birimi = "try" if yf_sembol.upper().endswith("-TRY") else "usd"
    ck = f"cg_fiyat_{cg_id}_{para_birimi}"
    cached = _c_al(ck, ttl=60)  # 1 dakika
    if cached is not None:
        return cached

    url  = f"{_cg_base()}/coins/{cg_id}"
    data = _get(url, params={
        "localization":   "false",
        "tickers":        "false",
        "community_data": "false",
        "developer_data": "false",
        "vs_currency":    para_birimi,
    }, headers=_cg_headers())

    if not data:
        _c_set(ck, {})
        return {}

    md  = data.get("market_data", {})
    cur = para_birimi
    pb  = "TRY" if cur == "try" else "USD"

    sonuc = {
        "kaynak":          "CoinGecko",
        "Isim":            data.get("name", ""),
        "Sembol":          data.get("symbol", "").upper(),
        "Para Birimi":     pb,
        "Fiyat":           f"{md.get('current_price', {}).get(cur, 0):,.6g} {pb}",
        "Degisim (24s %)": f"{md.get('price_change_percentage_24h', 0):+.2f}%",
        "Degisim (7g %)":  f"{md.get('price_change_percentage_7d', 0):+.2f}%",
        "Degisim (30g %)": f"{md.get('price_change_percentage_30d', 0):+.2f}%",
        "Piyasa Degeri":   f"{md.get('market_cap', {}).get(cur, 0)/1e9:.2f}B {pb}",
        "Hacim (24s)":     f"{md.get('total_volume', {}).get(cur, 0)/1e6:.2f}M {pb}",
        "Arz Dolaşım":     f"{md.get('circulating_supply', 0):,.0f}",
        "Maks Arz":        f"{md.get('max_supply', 0):,.0f}" if md.get("max_supply") else "Sınırsız",
        "ATH":             f"{md.get('ath', {}).get(cur, 0):,.6g} {pb}",
        "ATH Düşüş (%)":   f"{md.get('ath_change_percentage', {}).get(cur, 0):.1f}%",
        "52H Yüksek":      f"{md.get('high_24h', {}).get(cur, 0):,.6g} {pb}",
        "52H Düşük":       f"{md.get('low_24h', {}).get(cur, 0):,.6g} {pb}",
        "Sıralama":        f"#{data.get('market_cap_rank', '-')}",
        "Açıklama":        (data.get("description", {}).get("tr", "")
                            or data.get("description", {}).get("en", ""))[:200],
    }

    _c_set(ck, sonuc)
    return sonuc


def coingecko_gecmis(yf_sembol: str, gun: int = 30) -> list:
    """Son N günün kapanış fiyatı listesi (OHLCV alternatifi)."""
    cg_id = _CG_ID_MAP.get(yf_sembol.upper())
    if not cg_id:
        return []

    para_birimi = "try" if yf_sembol.upper().endswith("-TRY") else "usd"
    ck = f"cg_gecmis_{cg_id}_{gun}"
    cached = _c_al(ck, ttl=300)
    if cached is not None:
        return cached

    data = _get(
        f"{_cg_base()}/coins/{cg_id}/market_chart",
        params={"vs_currency": para_birimi, "days": gun, "interval": "daily"},
        headers=_cg_headers()
    )

    sonuc = []
    if data and data.get("prices"):
        for ts, fiyat in data["prices"]:
            tarih = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            sonuc.append({"tarih": tarih, "fiyat": fiyat})

    _c_set(ck, sonuc)
    return sonuc


def coingecko_trending() -> list:
    """CoinGecko'daki trend kriptoları."""
    ck = "cg_trending"
    cached = _c_al(ck, ttl=600)
    if cached is not None:
        return cached

    data = _get(f"{_cg_base()}/search/trending", headers=_cg_headers())
    sonuc = []
    if data and data.get("coins"):
        for item in data["coins"][:10]:
            c = item.get("item", {})
            sonuc.append({
                "isim":   c.get("name", ""),
                "sembol": c.get("symbol", ""),
                "rank":   c.get("market_cap_rank", "-"),
                "fiyat_usd": c.get("data", {}).get("price", ""),
                "degisim":   c.get("data", {}).get("price_change_percentage_24h", {}).get("usd", 0),
            })

    _c_set(ck, sonuc)
    return sonuc


# ═══════════════════════════════════════════════════════════════════
#  3. SEC EDGAR — ABD Bilanço (Tamamen Ücretsiz)
# ═══════════════════════════════════════════════════════════════════

_SEC_CIK_CACHE: dict = {}

def _sec_cik_bul(ticker: str) -> str:
    """Ticker → SEC CIK numarası."""
    t = ticker.upper().replace(".US", "").replace(".NASDAQ", "")
    if t in _SEC_CIK_CACHE:
        return _SEC_CIK_CACHE[t]

    headers = {"User-Agent": "finans-botu contact@finans-botu.com"}
    data = _get("https://efts.sec.gov/LATEST/search-index?q=%22ticker%22&dateRange=custom"
                f"&startdt=2020-01-01&enddt=2025-01-01&forms=10-K",
                headers=headers)

    # Daha güvenilir yol: tickers.json
    tickers_data = _get("https://www.sec.gov/files/company_tickers.json", headers=headers)
    if tickers_data:
        for entry in tickers_data.values():
            if entry.get("ticker", "").upper() == t:
                cik = str(entry["cik_str"]).zfill(10)
                _SEC_CIK_CACHE[t] = cik
                return cik

    return ""


def sec_bilanyo(ticker: str) -> dict:
    """
    SEC EDGAR'dan şirketin son bilanço verileri.
    Sadece ABD hisseleri için çalışır.
    Döner: {Toplam Varlıklar, Toplam Borç, Özsermaye, Nakit, ...}
    """
    ck = f"sec_{ticker}"
    cached = _c_al(ck, ttl=3600)
    if cached is not None:
        return cached

    cik = _sec_cik_bul(ticker)
    if not cik:
        _c_set(ck, {})
        return {}

    headers = {"User-Agent": "finans-botu contact@finans-botu.com"}
    url  = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    data = _get(url, headers=headers, timeout=15)

    if not data:
        _c_set(ck, {})
        return {}

    def _son_deger(concept: str) -> float:
        """us-gaap altındaki bir kavramın en son USD değerini döner."""
        try:
            entries = (data.get("facts", {})
                          .get("us-gaap", {})
                          .get(concept, {})
                          .get("units", {})
                          .get("USD", []))
            # 10-K formlarını tercih et, tarihe göre sırala
            yillik = [e for e in entries if e.get("form") in ("10-K", "20-F", "40-F")]
            if not yillik:
                yillik = entries
            if not yillik:
                return 0.0
            yillik_sorted = sorted(yillik, key=lambda x: x.get("end", ""), reverse=True)
            return float(yillik_sorted[0].get("val", 0))
        except Exception:
            return 0.0

    sonuc = {
        "kaynak":           "SEC EDGAR",
        "Toplam Varlıklar": _son_deger("Assets"),
        "Toplam Borç":      _son_deger("Liabilities"),
        "Özsermaye":        _son_deger("StockholdersEquity"),
        "Nakit":            _son_deger("CashAndCashEquivalentsAtCarryingValue"),
        "Net Gelir":        _son_deger("NetIncomeLoss"),
        "Toplam Gelir":     _son_deger("RevenueFromContractWithCustomerExcludingAssessedTax")
                            or _son_deger("Revenues"),
        "Kısa Vadeli Borç": _son_deger("LiabilitiesCurrent"),
        "Dönen Varlıklar":  _son_deger("AssetsCurrent"),
        "CapEx":            _son_deger("PaymentsToAcquirePropertyPlantAndEquipment"),
        "İşletme Nakit":    _son_deger("NetCashProvidedByUsedInOperatingActivities"),
    }

    # Sıfır değerleri temizle
    sonuc = {k: v for k, v in sonuc.items() if v != 0.0 or k == "kaynak"}

    _c_set(ck, sonuc)
    return sonuc


# ═══════════════════════════════════════════════════════════════════
#  4. FMP — Global Hisse Bilanço (250 istek/gün ücretsiz)
# ═══════════════════════════════════════════════════════════════════

def _fmp_base() -> str:
    return "https://financialmodelingprep.com/api/v3"

def fmp_bilanyo(sembol: str) -> dict:
    """
    FMP'den bilanço çeker. ABD + global borsalar.
    Sembol: AAPL, VOD.L, SAP.DE vb.
    """
    k = _key("FMP_API_KEY")
    if not k:
        return {}

    ck = f"fmp_bs_{sembol}"
    cached = _c_al(ck, ttl=3600)
    if cached is not None:
        return cached

    data = _get(f"{_fmp_base()}/balance-sheet-statement/{sembol}",
                params={"apikey": k, "limit": 1})

    if not data or not isinstance(data, list):
        _c_set(ck, {})
        return {}

    d = data[0]
    sonuc = {
        "kaynak":              "FMP",
        "Dönem":               d.get("date", ""),
        "Para Birimi":         d.get("reportedCurrency", ""),
        "Toplam Varlıklar":    d.get("totalAssets", 0),
        "Dönen Varlıklar":     d.get("totalCurrentAssets", 0),
        "Nakit":               d.get("cashAndCashEquivalents", 0),
        "Toplam Borç":         d.get("totalLiabilities", 0),
        "Kısa Vadeli Borç":    d.get("totalCurrentLiabilities", 0),
        "Uzun Vadeli Borç":    d.get("longTermDebt", 0),
        "Özsermaye":           d.get("totalStockholdersEquity", 0),
        "Net Borç":            d.get("netDebt", 0),
        "Stok":                d.get("inventory", 0),
    }

    _c_set(ck, sonuc)
    return sonuc


def fmp_gelir_tablosu(sembol: str) -> dict:
    """FMP'den gelir tablosu."""
    k = _key("FMP_API_KEY")
    if not k:
        return {}

    ck = f"fmp_is_{sembol}"
    cached = _c_al(ck, ttl=3600)
    if cached is not None:
        return cached

    data = _get(f"{_fmp_base()}/income-statement/{sembol}",
                params={"apikey": k, "limit": 1})

    if not data or not isinstance(data, list):
        _c_set(ck, {})
        return {}

    d = data[0]
    sonuc = {
        "kaynak":           "FMP",
        "Dönem":            d.get("date", ""),
        "Gelir":            d.get("revenue", 0),
        "Brüt Kâr":         d.get("grossProfit", 0),
        "EBITDA":           d.get("ebitda", 0),
        "İşletme Kârı":     d.get("operatingIncome", 0),
        "Net Kâr":          d.get("netIncome", 0),
        "EPS":              d.get("eps", 0),
        "Brüt Kâr Marjı":   d.get("grossProfitRatio", 0),
        "Net Kâr Marjı":    d.get("netProfitMargin", 0),
        "İşletme Marjı":    d.get("operatingIncomeRatio", 0),
    }

    _c_set(ck, sonuc)
    return sonuc


def fmp_profil(sembol: str) -> dict:
    """FMP'den şirket profili — yFinance'ta eksik gelen yabancı hisse bilgileri için."""
    k = _key("FMP_API_KEY")
    if not k:
        return {}

    ck = f"fmp_profil_{sembol}"
    cached = _c_al(ck, ttl=3600)
    if cached is not None:
        return cached

    data = _get(f"{_fmp_base()}/profile/{sembol}", params={"apikey": k})

    if not data or not isinstance(data, list):
        _c_set(ck, {})
        return {}

    d = data[0]
    sonuc = {
        "kaynak":        "FMP",
        "Ad":            d.get("companyName", ""),
        "Sektör":        d.get("sector", ""),
        "Endüstri":      d.get("industry", ""),
        "Ülke":          d.get("country", ""),
        "Borsa":         d.get("exchangeShortName", ""),
        "Para Birimi":   d.get("currency", ""),
        "Çalışan":       d.get("fullTimeEmployees", 0),
        "Fiyat":         d.get("price", 0),
        "Piyasa Değeri": d.get("mktCap", 0),
        "Beta":          d.get("beta", 0),
        "F/K":           d.get("pe", 0),
        "52H Yüksek":    d.get("range", "").split("-")[-1] if d.get("range") else "",
        "52H Düşük":     d.get("range", "").split("-")[0] if d.get("range") else "",
        "Açıklama":      (d.get("description", "") or "")[:300],
    }

    _c_set(ck, sonuc)
    return sonuc


def fmp_analist(sembol: str) -> dict:
    """FMP'den analist fiyat hedefleri."""
    k = _key("FMP_API_KEY")
    if not k:
        return {}

    ck = f"fmp_analist_{sembol}"
    cached = _c_al(ck, ttl=3600)
    if cached is not None:
        return cached

    data = _get(f"{_fmp_base()}/price-target-consensus/{sembol}",
                params={"apikey": k})

    if not data or not isinstance(data, list):
        _c_set(ck, {})
        return {}

    d = data[0]
    sonuc = {
        "Hedef Fiyat (Ort)": d.get("targetConsensus", 0),
        "Hedef Fiyat (Yük)": d.get("targetHigh", 0),
        "Hedef Fiyat (Düş)": d.get("targetLow", 0),
        "Hedef Fiyat (Med)": d.get("targetMedian", 0),
    }

    _c_set(ck, sonuc)
    return sonuc


# ═══════════════════════════════════════════════════════════════════
#  5. FINNHUB — Haberler & Insider (60 istek/dk ücretsiz)
# ═══════════════════════════════════════════════════════════════════

def _fh_sembol(sembol: str) -> str:
    """yFinance sembolünü Finnhub formatına çevir."""
    s = sembol.upper()
    donusum = {".L": ":LN", ".DE": ":GR", ".PA": ":FP",
               ".HK": ":HK", ".MI": ":IM", ".AS": ":NA"}
    for uzanti, fh in donusum.items():
        if s.endswith(uzanti):
            return s.replace(uzanti, "") + fh
    return s.replace(".IS", "")  # BIST: THYAO


def _fh_get(endpoint: str, params: dict) -> dict | list | None:
    k = _key("FINNHUB_API_KEY")
    if not k:
        return None
    params["token"] = k
    return _get(f"https://finnhub.io/api/v1/{endpoint}", params=params)


def finnhub_haberler(sembol: str, gun: int = 14) -> list:
    """Finnhub → yFinance fallback → borsapy fallback (BIST)."""
    ck = f"haber_{sembol}_{gun}"
    cached = _c_al(ck, ttl=300)
    if cached is not None:
        return cached

    haberler = []

    # 1. Finnhub
    if _key("FINNHUB_API_KEY"):
        bitis     = datetime.now().strftime("%Y-%m-%d")
        baslangic = (datetime.now() - timedelta(days=gun)).strftime("%Y-%m-%d")
        data = _fh_get("company-news", {
            "symbol": _fh_sembol(sembol),
            "from": baslangic, "to": bitis
        })
        if isinstance(data, list) and data:
            for item in data[:10]:
                ts    = item.get("datetime", 0)
                tarih = datetime.fromtimestamp(ts).strftime("%d.%m.%Y") if ts else "-"
                if item.get("headline"):
                    haberler.append({
                        "tarih":  tarih,
                        "baslik": item.get("headline", ""),
                        "kaynak": item.get("source", ""),
                        "url":    item.get("url", ""),
                        "kaynaktipi": "Finnhub",
                    })

    # 2. yFinance fallback
    if not haberler:
        try:
            import yfinance as yf
            yf_haberler = yf.Ticker(sembol).news or []
            for item in yf_haberler[:10]:
                ct    = item.get("content", {})
                ts    = ct.get("pubDate") or item.get("providerPublishTime")
                if isinstance(ts, (int, float)):
                    tarih = datetime.fromtimestamp(ts).strftime("%d.%m.%Y")
                elif ts:
                    tarih = str(ts)[:10]
                else:
                    tarih = "-"
                baslik = ct.get("title") or item.get("title", "")
                kaynak = (ct.get("provider", {}).get("displayName")
                          or item.get("publisher", ""))
                if baslik:
                    haberler.append({
                        "tarih":  tarih,
                        "baslik": baslik,
                        "kaynak": kaynak,
                        "url":    ct.get("canonicalUrl", {}).get("url", ""),
                        "kaynaktipi": "yFinance",
                    })
        except Exception:
            pass

    # 3. borsapy fallback (BIST)
    if not haberler and sembol.upper().endswith(".IS"):
        try:
            import borsapy as bp
            t = sembol.upper().replace(".IS", "")
            haberler_bp = bp.Ticker(t).news or []
            for item in (haberler_bp[:10] if isinstance(haberler_bp, list) else []):
                baslik = str(item.get("title", "") or item.get("headline", "") or "")
                tarih  = str(item.get("date", "") or item.get("publishedAt", "") or "")[:10]
                if baslik:
                    haberler.append({
                        "tarih":  tarih,
                        "baslik": baslik,
                        "kaynak": "KAP/borsapy",
                        "url":    item.get("url", ""),
                        "kaynaktipi": "borsapy",
                    })
        except Exception:
            pass

    _c_set(ck, haberler)
    return haberler


def finnhub_insider(sembol: str) -> list:
    """Finnhub → yFinance insider fallback."""
    ck = f"insider_{sembol}"
    cached = _c_al(ck, ttl=600)
    if cached is not None:
        return cached

    islemler = []

    # 1. Finnhub
    if _key("FINNHUB_API_KEY"):
        data = _fh_get("stock/insider-transactions", {"symbol": _fh_sembol(sembol)})
        for t in (data.get("data") or [])[:8] if isinstance(data, dict) else []:
            islemler.append({
                "tarih":  t.get("transactionDate", ""),
                "isim":   t.get("name", ""),
                "islem":  "ALIM" if (t.get("change", 0) or 0) > 0 else "SATIM",
                "adet":   abs(t.get("change", 0) or 0),
                "fiyat":  t.get("transactionPrice", 0) or 0,
                "kaynaktipi": "Finnhub",
            })

    # 2. yFinance fallback
    if not islemler:
        try:
            import yfinance as yf
            ins = yf.Ticker(sembol).insider_transactions
            if ins is not None and not ins.empty:
                for _, row in ins.head(8).iterrows():
                    try:
                        tarih = str(row.get("Start Date", row.get("Date", "")))[:10]
                        isim  = str(row.get("Insider", row.get("Name", "-")))
                        adet  = abs(int(row.get("Shares", 0) or 0))
                        deger = row.get("Value", 0) or 0
                        tip   = str(row.get("Transaction", "")).upper()
                        islem = "SATIM" if any(x in tip for x in ("SALE","SELL","SAT")) else "ALIM"
                        islemler.append({
                            "tarih": tarih, "isim": isim, "islem": islem,
                            "adet": adet,
                            "fiyat": float(deger) / adet if adet > 0 else 0,
                            "kaynaktipi": "yFinance",
                        })
                    except Exception:
                        continue
        except Exception:
            pass

    _c_set(ck, islemler)
    return islemler


def finnhub_kazanc(sembol: str) -> list:
    """Yaklaşan kazanç tarihleri."""
    ck = f"kazanc_{sembol}"
    cached = _c_al(ck, ttl=3600)
    if cached is not None:
        return cached

    if not _key("FINNHUB_API_KEY"):
        _c_set(ck, [])
        return []

    bitis     = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    baslangic = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    data = _fh_get("calendar/earnings", {
        "symbol": _fh_sembol(sembol),
        "from": baslangic, "to": bitis
    })

    sonuc = []
    for e in (data.get("earningsCalendar") or [])[:4] if isinstance(data, dict) else []:
        sonuc.append({
            "tarih":   e.get("date", ""),
            "saat":    e.get("hour", ""),
            "tahmin":  e.get("epsEstimate"),
            "gercek":  e.get("epsActual"),
        })

    _c_set(ck, sonuc)
    return sonuc


# ═══════════════════════════════════════════════════════════════════
#  6. APEWISDOM — Reddit/WSB Trend (Ücretsiz)
# ═══════════════════════════════════════════════════════════════════

def reddit_trend() -> list:
    """Reddit WSB + Stocks'ta en çok konuşulan hisseler."""
    ck = "reddit_trend"
    cached = _c_al(ck, ttl=600)
    if cached is not None:
        return cached

    data = _get("https://apewisdom.io/api/v1.0/filter/all-stocks/page/1", timeout=8)
    sonuc = []
    if data and data.get("results"):
        for item in data["results"][:15]:
            sonuc.append({
                "sembol":  item.get("ticker", ""),
                "isim":    item.get("name", ""),
                "mention": item.get("mentions", 0),
                "degisim": item.get("mentions_24h_ago", 0),
                "rank":    item.get("rank", 0),
            })

    _c_set(ck, sonuc)
    return sonuc


def reddit_kripto_trend() -> list:
    """Reddit'te en çok konuşulan kriptolar."""
    ck = "reddit_kripto"
    cached = _c_al(ck, ttl=600)
    if cached is not None:
        return cached

    data = _get("https://apewisdom.io/api/v1.0/filter/all-crypto/page/1", timeout=8)
    sonuc = []
    if data and data.get("results"):
        for item in data["results"][:10]:
            sonuc.append({
                "sembol":  item.get("ticker", ""),
                "isim":    item.get("name", ""),
                "mention": item.get("mentions", 0),
                "rank":    item.get("rank", 0),
            })

    _c_set(ck, sonuc)
    return sonuc


# ═══════════════════════════════════════════════════════════════════
#  7. ALPHAVANTAGE — Yedek Fiyat Kaynağı (25 istek/gün ücretsiz)
# ═══════════════════════════════════════════════════════════════════

def alphavantage_fiyat(sembol: str) -> dict:
    """yFinance ve CoinGecko çalışmazsa son çare."""
    k = _key("ALPHAVANTAGE_API_KEY")
    if not k:
        return {}

    ck = f"av_{sembol}"
    cached = _c_al(ck, ttl=120)
    if cached is not None:
        return cached

    data = _get("https://www.alphavantage.co/query", params={
        "function": "GLOBAL_QUOTE",
        "symbol": sembol,
        "apikey": k,
    })

    q = (data or {}).get("Global Quote", {})
    sonuc = {}
    if q.get("05. price"):
        sonuc = {
            "kaynak":   "AlphaVantage",
            "fiyat":    float(q.get("05. price", 0)),
            "degisim":  float(q.get("09. change", 0)),
            "degisim_pct": q.get("10. change percent", ""),
            "hacim":    int(q.get("06. volume", 0)),
            "onceki":   float(q.get("08. previous close", 0)),
        }

    _c_set(ck, sonuc)
    return sonuc


# ═══════════════════════════════════════════════════════════════════
#  8. YÜKSEK SEVİYE API'ler — main.py'den çağrılan fonksiyonlar
# ═══════════════════════════════════════════════════════════════════

def kripto_zengin_veri(yf_sembol: str) -> dict:
    """
    CoinGecko birincil, yFinance fallback.
    Kripto analizinde piyasa_analiz.py'ye ek zengin veri sağlar.
    """
    cg = coingecko_fiyat(yf_sembol)
    return cg  # {} dönerse piyasa_analiz.py yFinance'ı kullanmaya devam eder


def hisse_ek_veri(sembol: str) -> dict:
    """
    Yabancı hisseler için FMP profil + SEC bilanço birleşimi.
    BIST hisseleri için boş döner (borsapy temel_analiz.py'de kullanılıyor).
    """
    if sembol.upper().endswith(".IS"):
        return {}

    sonuc = {}

    # FMP profil (yFinance'ta olmayan yabancı hisse bilgileri)
    profil = fmp_profil(sembol)
    if profil:
        sonuc.update(profil)

    # SEC EDGAR (ABD hisseleri için bilanço doğrulama)
    t = sembol.upper().replace(".US", "")
    if "." not in t:  # Uzantısız = ABD hissesi
        sec = sec_bilanyo(t)
        if sec:
            sonuc["SEC_bilanyo"] = sec

    return sonuc


def ai_icin_haber_ozeti(sembol: str) -> str:
    """AI yorumuna eklenmek üzere haber özeti."""
    haberler = finnhub_haberler(sembol, gun=7)
    if not haberler:
        return ""
    satirlar = ["=== SON HABERLER (7 gün) ==="]
    for hbr in haberler[:5]:
        if hbr.get("baslik"):
            satirlar.append(f"• [{hbr['tarih']}] {hbr['baslik']} ({hbr.get('kaynak','')})")
    return "\n".join(satirlar)


def durum_raporu() -> str:
    """Tüm API'lerin aktif/pasif durumunu gösterir."""
    satirlar = ["🔌 API Durum Raporu\n"]
    kontroller = [
        ("Finnhub",       "FINNHUB_API_KEY",      "Haberler, Insider, Kazanç Takvimi"),
        ("CoinGecko",     "COINGECKO_API_KEY",     "Kripto Fiyat, Trend, ATH"),
        ("FMP",           "FMP_API_KEY",           "Yabancı Hisse Bilanço + Profil"),
        ("AlphaVantage",  "ALPHAVANTAGE_API_KEY",  "Yedek Fiyat Kaynağı"),
        ("OpenFIGI",      "OPENFIGI_API_KEY",      "Sembol Çözümleme (key'siz de çalışır)"),
    ]
    for ad, env, aciklama in kontroller:
        k = _key(env)
        durum = "✅ Aktif" if k else "⚠️ Key yok"
        satirlar.append(f"{durum}  {ad:15} — {aciklama}")

    # Key'siz çalışanlar
    satirlar.append("\n✅ Aktif  SEC EDGAR    — ABD Bilanço (key'siz)")
    satirlar.append("✅ Aktif  borsapy      — KAP/BIST (key'siz)")
    satirlar.append("✅ Aktif  ApeWisdom    — Reddit Trend (key'siz)")

    return "\n".join(satirlar)
