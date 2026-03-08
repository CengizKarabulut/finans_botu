"""
finnhub_veri.py — Finnhub + OpenFIGI + Alpha Vantage entegrasyonu.

Finnhub  : Haberler, insider işlemler, kazanç takvimi, sentiment (60 istek/dk ücretsiz)
OpenFIGI : Sembol doğrulama/çözümleme (tamamen ücretsiz, sınırsız)
AlphaVantage: Yedek fiyat kaynağı (25 istek/gün ücretsiz)

API Key'ler ortam değişkeninden alınır:
  export FINNHUB_API_KEY="..."
  export ALPHAVANTAGE_API_KEY="..."
  OpenFIGI key'siz de çalışır.
"""

import os
import time
import requests
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
#  BASIT CACHE (işlem boyunca geçerli)
# ─────────────────────────────────────────────
_cache: dict = {}
_CACHE_TTL = 300  # 5 dakika

def _cache_al(key: str):
    item = _cache.get(key)
    if item and (time.time() - item["ts"]) < _CACHE_TTL:
        return item["veri"]
    return None

def _cache_kaydet(key: str, veri):
    _cache[key] = {"veri": veri, "ts": time.time()}


# ─────────────────────────────────────────────
#  FINNHUB
# ─────────────────────────────────────────────

def _finnhub_key() -> str:
    return os.environ.get("FINNHUB_API_KEY", "")

def _finnhub_get(endpoint: str, params: dict) -> dict:
    """Finnhub REST çağrısı."""
    key = _finnhub_key()
    if not key:
        return {}
    try:
        params["token"] = key
        r = requests.get(f"https://finnhub.io/api/v1/{endpoint}",
                         params=params, timeout=8)
        if r.status_code == 200:
            return r.json()
        return {}
    except Exception:
        return {}


def finnhub_haberler(sembol: str, gun: int = 7) -> list:
    """
    Hisse için son N günün haberlerini döner.
    Finnhub key varsa Finnhub, yoksa yFinance news fallback kullanır.
    """
    cache_key = f"haber_{sembol}_{gun}"
    cached = _cache_al(cache_key)
    if cached is not None:
        return cached

    haberler = []

    # 1. Finnhub (key varsa)
    if _finnhub_key():
        bitis  = datetime.now().strftime("%Y-%m-%d")
        baslangic = (datetime.now() - timedelta(days=gun)).strftime("%Y-%m-%d")
        fh_sembol = _sembol_finnhub_formatina_cevir(sembol)
        data = _finnhub_get("company-news", {
            "symbol": fh_sembol,
            "from": baslangic,
            "to": bitis
        })
        if isinstance(data, list) and data:
            for h in data[:10]:
                haberler.append({
                    "tarih":  datetime.fromtimestamp(h.get("datetime", 0)).strftime("%d.%m.%Y"),
                    "baslik": h.get("headline", ""),
                    "kaynak": h.get("source", ""),
                    "url":    h.get("url", ""),
                    "kaynak_tipi": "Finnhub",
                })

    # 2. yFinance fallback (key yoksa veya Finnhub boş döndüyse)
    if not haberler:
        try:
            import yfinance as yf
            ticker = yf.Ticker(sembol)
            yf_haberler = ticker.news or []
            for h in yf_haberler[:10]:
                # Zaman damgası
                ts = h.get("content", {}).get("pubDate") or h.get("providerPublishTime")
                if ts:
                    try:
                        if isinstance(ts, (int, float)):
                            tarih = datetime.fromtimestamp(ts).strftime("%d.%m.%Y")
                        else:
                            tarih = str(ts)[:10]
                    except Exception:
                        tarih = "-"
                else:
                    tarih = "-"

                baslik = (h.get("content", {}).get("title")
                          or h.get("title", ""))
                kaynak = (h.get("content", {}).get("provider", {}).get("displayName")
                          or h.get("publisher", ""))
                url    = (h.get("content", {}).get("canonicalUrl", {}).get("url")
                          or h.get("link", ""))

                if baslik:
                    haberler.append({
                        "tarih":  tarih,
                        "baslik": baslik,
                        "kaynak": kaynak,
                        "url":    url,
                        "kaynak_tipi": "yFinance",
                    })
        except Exception:
            pass

    _cache_kaydet(cache_key, haberler)
    return haberler


def finnhub_insider(sembol: str) -> list:
    """
    Son insider alım/satım işlemleri.
    Finnhub key varsa Finnhub, yoksa yFinance insider_transactions fallback.
    """
    cache_key = f"insider_{sembol}"
    cached = _cache_al(cache_key)
    if cached is not None:
        return cached

    islemler = []

    # 1. Finnhub (key varsa)
    if _finnhub_key():
        fh_sembol = _sembol_finnhub_formatina_cevir(sembol)
        data = _finnhub_get("stock/insider-transactions", {"symbol": fh_sembol})
        for t in (data.get("data") or [])[:8]:
            islemler.append({
                "tarih": t.get("transactionDate", ""),
                "isim":  t.get("name", ""),
                "islem": "ALIM" if (t.get("change", 0) or 0) > 0 else "SATIM",
                "adet":  abs(t.get("change", 0) or 0),
                "fiyat": t.get("transactionPrice", 0) or 0,
                "kaynak_tipi": "Finnhub",
            })

    # 2. yFinance fallback
    if not islemler:
        try:
            import yfinance as yf
            ticker = yf.Ticker(sembol)
            # major_holders veya insider_transactions
            ins = ticker.insider_transactions
            if ins is not None and not ins.empty:
                for _, row in ins.head(8).iterrows():
                    try:
                        tarih = str(row.get("Start Date", row.get("Date", "")))[:10]
                        isim  = str(row.get("Insider", row.get("Name", "-")))
                        adet  = abs(int(row.get("Shares", 0) or 0))
                        deger = row.get("Value", row.get("Transaction Value", 0)) or 0
                        islem_tip = str(row.get("Transaction", row.get("Type", ""))).upper()
                        if "SALE" in islem_tip or "SELL" in islem_tip or "SAT" in islem_tip:
                            islem = "SATIM"
                        else:
                            islem = "ALIM"
                        islemler.append({
                            "tarih": tarih,
                            "isim":  isim,
                            "islem": islem,
                            "adet":  adet,
                            "fiyat": float(deger) / adet if adet > 0 else 0,
                            "kaynak_tipi": "yFinance",
                        })
                    except Exception:
                        continue
        except Exception:
            pass

    _cache_kaydet(cache_key, islemler)
    return islemler


def finnhub_kazanc_takvimi(sembol: str) -> list:
    """Yaklaşan/geçmiş kazanç tarihleri."""
    cache_key = f"kazanc_{sembol}"
    cached = _cache_al(cache_key)
    if cached is not None:
        return cached

    fh_sembol = _sembol_finnhub_formatina_cevir(sembol)
    bitis  = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    baslangic = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    data = _finnhub_get("calendar/earnings", {
        "symbol": fh_sembol,
        "from": baslangic,
        "to": bitis
    })

    sonuclar = []
    for e in (data.get("earningsCalendar") or [])[:4]:
        sonuclar.append({
            "tarih":   e.get("date", ""),
            "saat":    e.get("hour", ""),
            "tahmin":  e.get("epsEstimate"),
            "gercek":  e.get("epsActual"),
        })

    _cache_kaydet(cache_key, sonuclar)
    return sonuclar


def finnhub_sentiment(sembol: str) -> dict:
    """Reddit/sosyal medya sentiment skoru."""
    cache_key = f"sentiment_{sembol}"
    cached = _cache_al(cache_key)
    if cached is not None:
        return cached

    fh_sembol = _sembol_finnhub_formatina_cevir(sembol)
    data = _finnhub_get("stock/social-sentiment", {
        "symbol": fh_sembol,
        "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    })

    # Reddit özeti
    reddit = data.get("reddit", [])
    if reddit:
        son = reddit[-1] if reddit else {}
        sonuc = {
            "platform": "Reddit",
            "mention":  son.get("mention", 0),
            "pozitif":  son.get("positiveMention", 0),
            "negatif":  son.get("negativeMention", 0),
        }
    else:
        sonuc = {}

    _cache_kaydet(cache_key, sonuc)
    return sonuc


def finnhub_genel_sentiment() -> list:
    """
    WSB (WallStreetBets) üzerinde en çok konuşulan hisseler.
    Tradestie ölü, yerine ApeWisdom kullanılıyor.
    """
    cache_key = "wsb_trending"
    cached = _cache_al(cache_key)
    if cached is not None:
        return cached

    try:
        r = requests.get("https://apewisdom.io/api/v1.0/filter/all-stocks/page/1",
                         timeout=8)
        if r.status_code == 200:
            data = r.json().get("results", [])[:10]
            sonuc = [{"sembol": d["ticker"], "mention": d.get("mentions", 0),
                      "rank": d.get("rank", 0)} for d in data]
            _cache_kaydet(cache_key, sonuc)
            return sonuc
    except Exception:
        pass
    return []


# ─────────────────────────────────────────────
#  OPENFIGI — Sembol Çözümleme
# ─────────────────────────────────────────────

def openfigi_sembol_bilgisi(ticker: str, borse_kodu: str = "US") -> dict:
    """
    OpenFIGI ile ticker → şirket adı, borsa, güvenlik tipi.
    Tamamen ücretsiz ve sınırsız.
    """
    cache_key = f"figi_{ticker}_{borse_kodu}"
    cached = _cache_al(cache_key)
    if cached is not None:
        return cached

    try:
        r = requests.post(
            "https://api.openfigi.com/v3/mapping",
            json=[{"idType": "TICKER", "idValue": ticker, "exchCode": borse_kodu}],
            headers={"Content-Type": "application/json"},
            timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            if data and data[0].get("data"):
                ilk = data[0]["data"][0]
                sonuc = {
                    "ad":         ilk.get("name", ""),
                    "borsa":      ilk.get("exchCode", ""),
                    "tip":        ilk.get("securityType", ""),
                    "para_birimi": ilk.get("currency", ""),
                    "figi":       ilk.get("figi", ""),
                }
                _cache_kaydet(cache_key, sonuc)
                return sonuc
    except Exception:
        pass
    return {}


# ─────────────────────────────────────────────
#  ALPHA VANTAGE — Yedek Fiyat Kaynağı
# ─────────────────────────────────────────────

def _av_key() -> str:
    return os.environ.get("ALPHAVANTAGE_API_KEY", "demo")

def alphavantage_fiyat(sembol: str) -> dict:
    """
    Alpha Vantage'dan anlık fiyat çeker.
    yFinance çalışmazsa fallback olarak kullanılır.
    Günlük limit: 25 istek (ücretsiz)
    """
    cache_key = f"av_{sembol}"
    cached = _cache_al(cache_key)
    if cached is not None:
        return cached

    try:
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": sembol,
                "apikey": _av_key()
            },
            timeout=8
        )
        if r.status_code == 200:
            q = r.json().get("Global Quote", {})
            if q.get("05. price"):
                sonuc = {
                    "fiyat":    float(q.get("05. price", 0)),
                    "degisim":  float(q.get("09. change", 0)),
                    "degisim_pct": q.get("10. change percent", ""),
                    "hacim":    int(q.get("06. volume", 0)),
                    "onceki":   float(q.get("08. previous close", 0)),
                }
                _cache_kaydet(cache_key, sonuc)
                return sonuc
    except Exception:
        pass
    return {}


# ─────────────────────────────────────────────
#  YARDIMCI: Sembol Format Dönüşümü
# ─────────────────────────────────────────────

def _sembol_finnhub_formatina_cevir(sembol: str) -> str:
    """
    BIST: THYAO.IS → Finnhub'da çalışmaz (sadece ABD/global hisseler)
    ABD:  AAPL     → AAPL (doğrudan)
    Londra: SHEL.L → SHEL:LN
    Frankfurt: SAP.DE → SAP:GR
    """
    s = sembol.upper()
    if s.endswith(".IS"):
        # BIST hisseleri Finnhub'da genellikle desteklenmez
        return s.replace(".IS", "")
    elif s.endswith(".L"):
        return s.replace(".L", "") + ":LN"
    elif s.endswith(".DE"):
        return s.replace(".DE", "") + ":GR"
    elif s.endswith(".PA"):
        return s.replace(".PA", "") + ":FP"
    elif s.endswith(".HK"):
        return s.replace(".HK", "") + ":HK"
    return s


# ─────────────────────────────────────────────
#  AI İÇİN HABER ÖZETİ
# ─────────────────────────────────────────────

def ai_icin_haber_ozeti(sembol: str) -> str:
    """
    AI yorumuna eklenecek haber özetini hazırlar.
    Boş string döner eğer haber yoksa.
    """
    haberler = finnhub_haberler(sembol, gun=7)
    if not haberler:
        return ""

    satirlar = ["=== SON HABERLER (7 gün) ==="]
    for h in haberler[:5]:
        if h["baslik"]:
            satirlar.append(f"• [{h['tarih']}] {h['baslik']} ({h['kaynak']})")

    return "\n".join(satirlar)
