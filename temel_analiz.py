import os
import json
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from cache_yonetici import taze_ticker


# ─────────────────────────────────────────────
#  SEKTÖR LİSTESİ (JSON'dan yükle)
# ─────────────────────────────────────────────

_SEKTOR_LISTESI: dict = {}
_SEKTOR_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sektor_listesi.json")

def _sektor_listesi_yukle():
    global _SEKTOR_LISTESI
    if _SEKTOR_LISTESI:
        return
    try:
        with open(_SEKTOR_JSON, "r", encoding="utf-8") as f:
            _SEKTOR_LISTESI = json.load(f)
    except Exception:
        _SEKTOR_LISTESI = {}

def _sektor_bul(ticker_symbol: str) -> str:
    """Hissenin sektörünü JSON'dan döner."""
    _sektor_listesi_yukle()
    t = ticker_symbol.upper().replace(".IS", "")
    return _SEKTOR_LISTESI.get(t, {}).get("sector", "")

def _sektordeki_hisseler(sektor: str, hisse_kodu: str) -> list:
    """Aynı sektördeki diğer hisseleri döner."""
    _sektor_listesi_yukle()
    t = hisse_kodu.upper().replace(".IS", "")
    return [
        k for k, v in _SEKTOR_LISTESI.items()
        if v.get("sector", "") == sektor and k != t
    ]


# ─────────────────────────────────────────────
#  SEKTÖREL KARŞILAŞTIRMA (borsapy fast_info)
# ─────────────────────────────────────────────

def _sektörel_karsilastirma(hisse_kodu: str, sektor: str) -> dict:
    """
    Aynı sektördeki hisselerin F/K, PD/DD, FD/FAVÖK ortalamalarını hesaplar.
    borsapy fast_info kullanır — hızlı ve hafif.
    """
    if not sektor:
        return {}

    try:
        import borsapy as bp
    except ImportError:
        return {}

    diger_hisseler = _sektordeki_hisseler(sektor, hisse_kodu)
    if not diger_hisseler:
        return {}

    fk_list, pddd_list, fdfavok_list = [], [], []

    def _cek(ticker):
        try:
            fi = bp.Ticker(ticker).fast_info
            return {
                "fk":      getattr(fi, "pe_ratio", None),
                "pddd":    getattr(fi, "pb_ratio", None),
                "fdfavok": None,  # fast_info'da yok, info'dan çekmek yavaş
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=10) as ex:
        gelecekler = {ex.submit(_cek, t): t for t in diger_hisseler}
        for f in as_completed(gelecekler):
            res = f.result()
            if res:
                if res["fk"] and float(res["fk"]) > 0:
                    fk_list.append(float(res["fk"]))
                if res["pddd"] and float(res["pddd"]) > 0:
                    pddd_list.append(float(res["pddd"]))

    sonuc = {"_sektor_hisse_sayisi": len(diger_hisseler)}
    if fk_list:
        sonuc["Sektör Ort. F/K"]    = round(np.median(fk_list), 2)
        sonuc["Sektör Min F/K"]     = round(min(fk_list), 2)
        sonuc["Sektör Maks F/K"]    = round(max(fk_list), 2)
    if pddd_list:
        sonuc["Sektör Ort. PD/DD"]  = round(np.median(pddd_list), 2)
        sonuc["Sektör Min PD/DD"]   = round(min(pddd_list), 2)
        sonuc["Sektör Maks PD/DD"]  = round(max(pddd_list), 2)

    return sonuc


# ─────────────────────────────────────────────
#  borsapy EK VERİLER
# ─────────────────────────────────────────────

def _carpan_dogrula(yf_deger: float, bp_deger: float, alan_adi: str,
                    esik_pct: float = 10.0) -> dict | None:
    """
    yFinance ve borsapy değerini karşılaştırır.
    Fark > esik_pct% ise uyarı dict döner, aksi halde None.
    """
    try:
        if not yf_deger or not bp_deger or yf_deger == 0 or bp_deger == 0:
            return None
        fark_pct = abs(yf_deger - bp_deger) / abs(yf_deger) * 100
        if fark_pct > esik_pct:
            return {
                "alan":    alan_adi,
                "yfinance": round(yf_deger, 2),
                "borsapy":  round(bp_deger, 2),
                "fark_pct": round(fark_pct, 1),
            }
    except Exception:
        pass
    return None


def _borsapy_verileri(ticker_symbol: str, yf_info: dict | None = None) -> dict:
    """
    borsapy'den: fiili dolaşım, yabancı oranı, analist hedefleri, ana ortaklar.
    yf_info verilirse F/K, PD/DD, Piyasa Değeri, 52H gibi çarpanları karşılaştırır.
    Sadece .IS uzantılı (BIST) hisseler için çalışır.
    """
    if not ticker_symbol.upper().endswith(".IS"):
        return {}
    try:
        import borsapy as bp
        t = ticker_symbol.upper().replace(".IS", "")
        h = bp.Ticker(t)
        sonuc = {}

        # ── fast_info ──────────────────────────────────────────────────────────
        fi = h.fast_info
        ff = getattr(fi, "free_float",    None)
        fr = getattr(fi, "foreign_ratio", None)
        bp_fk      = getattr(fi, "pe_ratio",      None)
        bp_pddd    = getattr(fi, "pb_ratio",       None)
        bp_mkcap   = getattr(fi, "market_cap",     None)
        bp_52h     = getattr(fi, "year_high",      None)
        bp_52l     = getattr(fi, "year_low",       None)

        if ff is not None:
            sonuc["Fiili Dolaşım (%)"] = round(float(ff), 2)
        if fr is not None:
            sonuc["Yabancı Oranı (%)"] = round(float(fr), 2)

        # ── Çarpan Doğrulama (yf_info verilmişse) ────────────────────────────
        uyarilar = []
        if yf_info:
            yf_fk    = float(yf_info.get("trailingPE")    or 0)
            yf_pddd  = float(yf_info.get("priceToBook")   or 0)
            yf_mkcap = float(yf_info.get("marketCap")     or 0)
            yf_52h   = float(yf_info.get("fiftyTwoWeekHigh") or 0)
            yf_52l   = float(yf_info.get("fiftyTwoWeekLow")  or 0)

            kontroller = [
                (yf_fk,    bp_fk,    "F/K",            15.0),  # F/K için %15 tolerans
                (yf_pddd,  bp_pddd,  "PD/DD",          15.0),
                (yf_mkcap, bp_mkcap, "Piyasa Değeri",   5.0),  # piyasa değeri %5
                (yf_52h,   bp_52h,   "52H Yüksek",      3.0),
                (yf_52l,   bp_52l,   "52H Düşük",       3.0),
            ]

            for yf_v, bp_v, ad, esik in kontroller:
                if bp_v is not None:
                    uyari = _carpan_dogrula(yf_v, float(bp_v), ad, esik)
                    if uyari:
                        uyarilar.append(
                            f"{uyari['alan']}: yF={uyari['yfinance']} bp={uyari['borsapy']} "
                            f"(Δ%{uyari['fark_pct']})"
                        )

        if uyarilar:
            sonuc["⚠️ Veri Tutarsızlığı"] = " | ".join(uyarilar)
        else:
            sonuc["✅ Veri Doğrulaması"] = "yFinance ↔ borsapy tutarlı"

        # ── Analist hedef fiyatları ───────────────────────────────────────────
        try:
            apt = h.analyst_price_targets
            if apt and isinstance(apt, dict):
                n = apt.get("numberOfAnalysts", 0)
                if n and int(n) > 0:
                    sonuc["Analist Hedef — Ort (TL)"]  = apt.get("mean", "-")
                    sonuc["Analist Hedef — Med (TL)"]  = apt.get("median", "-")
                    sonuc["Analist Hedef — Min (TL)"]  = apt.get("low", "-")
                    sonuc["Analist Hedef — Maks (TL)"] = apt.get("high", "-")
                    sonuc["Analist Sayısı"]             = int(n)
        except Exception:
            pass

        # ── Ana ortaklar ──────────────────────────────────────────────────────
        try:
            mh = h.major_holders
            if mh is not None and not mh.empty:
                satirlar = []
                for holder, row in mh.iterrows():
                    pct = row.iloc[0]
                    satirlar.append(f"{holder}: %{pct}")
                sonuc["Ana Ortaklar"] = " | ".join(satirlar[:4])
        except Exception:
            pass

        return sonuc

    except Exception:
        return {}


# ─────────────────────────────────────────────
#  YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def get_val(df: pd.DataFrame, row_names: list, col_index: int = 0) -> float:
    for name in row_names:
        try:
            if name in df.index:
                val = df.loc[name].iloc[col_index]
                if not pd.isna(val):
                    return float(val)
        except Exception:
            pass
    return 0.0


def safe_div(pay, payda, multiply: float = 1, fallback: float = 0.0) -> float:
    try:
        if payda and payda != 0:
            return round((pay / payda) * multiply, 2)
    except Exception:
        pass
    return fallback


def pct_change(yeni, eski) -> float:
    if eski and eski != 0:
        return round((yeni - eski) / abs(eski) * 100, 2)
    return 0.0


def calc_beta(ticker_symbol: str, stock_returns: pd.Series, period: str = "1y") -> float:
    try:
        if stock_returns is None or len(stock_returns) < 30:
            return 0.0
        benchmark = "XU100.IS" if ticker_symbol.upper().endswith(".IS") else "^GSPC"
        m = taze_ticker(benchmark).history(period=period)["Close"].pct_change().dropna()
        if len(m) < 30:
            return 0.0
        df = pd.concat([stock_returns, m], axis=1, join="inner").dropna()
        if len(df) < 30:
            return 0.0
        df.columns = ["Stock", "Market"]
        cov = df.cov().iloc[0, 1]
        var = df["Market"].var()
        return round(cov / var, 3) if var and var > 0 else 0.0
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
#  ANA FONKSİYON
# ─────────────────────────────────────────────

def temel_analiz_yap(ticker_symbol: str) -> dict:
    hisse = taze_ticker(ticker_symbol)

    def _fetch(attr):
        return attr, getattr(hisse, attr)

    finansal_attrs = [
        "balance_sheet", "financials", "cashflow",
        "quarterly_balance_sheet", "quarterly_financials", "quarterly_cashflow",
        "info"
    ]

    sonuclar_fetch = {}
    with ThreadPoolExecutor(max_workers=7) as ex:
        gelecekler = {ex.submit(_fetch, a): a for a in finansal_attrs}
        for f in as_completed(gelecekler):
            attr, deger = f.result()
            sonuclar_fetch[attr] = deger

    bs    = sonuclar_fetch["balance_sheet"]
    inc   = sonuclar_fetch["financials"]
    cf    = sonuclar_fetch["cashflow"]
    q_bs  = sonuclar_fetch["quarterly_balance_sheet"]
    q_inc = sonuclar_fetch["quarterly_financials"]
    q_cf  = sonuclar_fetch["quarterly_cashflow"]
    info  = sonuclar_fetch["info"]

    if bs is None or bs.empty or inc is None or inc.empty:
        return {"Hata": "Finansal veri bulunamadı."}

    # Yıllık Gelir Tablosu
    satis_y0       = get_val(inc, ["Total Revenue", "Operating Revenue"], 0)
    satis_y1       = get_val(inc, ["Total Revenue", "Operating Revenue"], 1)
    net_kar_y0     = get_val(inc, ["Net Income"], 0)
    net_kar_y1     = get_val(inc, ["Net Income"], 1)
    cogs_y0        = get_val(inc, ["Cost Of Revenue"], 0)
    brut_kar_y0    = get_val(inc, ["Gross Profit"], 0) or (satis_y0 - cogs_y0)
    isletme_kari   = get_val(inc, ["Operating Income", "Total Operating Income As Reported"], 0)
    ebit           = get_val(inc, ["EBIT"], 0) or isletme_kari
    faiz_gideri    = abs(get_val(inc, ["Interest Expense", "Interest Expense Non Operating"], 0))
    vergi_gideri   = abs(get_val(inc, ["Tax Provision", "Income Tax Expense"], 0))

    # Yıllık Nakit Akışı
    amortisman     = get_val(cf, ["Depreciation And Amortization", "Depreciation Amortization Depletion"], 0)
    op_nakit       = get_val(cf, ["Operating Cash Flow"], 0)
    capex          = abs(get_val(cf, ["Capital Expenditure", "Purchase Of Plant And Equipment", "Purchases Of Property Plant And Equipment"], 0))
    temettu        = abs(get_val(cf, ["Cash Dividends Paid", "Common Stock Dividend Paid"], 0))
    ebitda         = float(info.get("ebitda") or 0) or (ebit + amortisman)

    # Yıllık Bilanço
    oz_sermaye_y0  = get_val(bs, ["Stockholders Equity", "Total Equity Gross Minority Interest"], 0)
    oz_sermaye_y1  = get_val(bs, ["Stockholders Equity", "Total Equity Gross Minority Interest"], 1)
    varliklar_y0   = get_val(bs, ["Total Assets"], 0)
    varliklar_y1   = get_val(bs, ["Total Assets"], 1)
    donen          = get_val(bs, ["Current Assets", "Total Current Assets"], 0)
    kisa_borc      = get_val(bs, ["Current Liabilities", "Total Current Liabilities Net Minority Interest"], 0)
    stok_y0        = get_val(bs, ["Inventory", "Inventories", "Finished Goods"], 0)
    stok_y1        = get_val(bs, ["Inventory", "Inventories", "Finished Goods"], 1)
    alacak_y0      = get_val(bs, ["Accounts Receivable", "Net Receivables", "Receivables", "Trade And Other Receivables Non Current"], 0)
    alacak_y1      = get_val(bs, ["Accounts Receivable", "Net Receivables", "Receivables", "Trade And Other Receivables Non Current"], 1)
    nakit          = get_val(bs, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash And Short Term Investments"], 0)
    toplam_borc    = get_val(bs, ["Total Debt", "Long Term Debt And Capital Lease Obligation"], 0)

    # Çeyreklik Veriler
    def _q_ilk_dolu(df_q, row_names):
        for i in range(4):
            v = get_val(df_q, row_names, i)
            if v != 0:
                return v, i
        return 0.0, 0

    q_satis_q0, q0_idx = _q_ilk_dolu(q_inc, ["Total Revenue", "Operating Revenue"])
    q_satis_q1         = get_val(q_inc, ["Total Revenue", "Operating Revenue"], q0_idx + 1)
    q_satis_q4         = get_val(q_inc, ["Total Revenue", "Operating Revenue"], q0_idx + 4)
    q_net_kar_q0       = get_val(q_inc, ["Net Income"], q0_idx)
    q_cogs_q0          = get_val(q_inc, ["Cost Of Revenue"], q0_idx)
    q_brut_kar_q0      = get_val(q_inc, ["Gross Profit"], q0_idx) or (q_satis_q0 - q_cogs_q0)
    q_ebit_q0          = get_val(q_inc, ["EBIT", "Operating Income"], q0_idx)
    q_amortisman       = get_val(q_cf,  ["Depreciation And Amortization"], q0_idx)
    q_ebitda_q0        = q_ebit_q0 + q_amortisman
    q_oz_sermaye       = get_val(q_bs,  ["Stockholders Equity", "Total Equity Gross Minority Interest"], 0)

    # Piyasa Verileri
    fiyat          = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
    piyasa_degeri  = float(info.get("marketCap") or 0)
    hisse_sayisi   = float(info.get("sharesOutstanding") or 1)
    kur_deg_y      = float(info.get("enterpriseValue") or 0)
    eps            = float(info.get("trailingEps") or 0) or safe_div(net_kar_y0, hisse_sayisi)

    # Türetilmiş Değerler
    vergi_orani    = safe_div(vergi_gideri, ebit) if ebit > 0 else 0.20
    yat_sermaye    = toplam_borc + oz_sermaye_y0 - nakit
    nopat          = ebit * (1 - vergi_orani)
    fcf            = op_nakit - capex
    defter_hisse   = safe_div(oz_sermaye_y0, hisse_sayisi)
    satis_hisse    = safe_div(satis_y0, hisse_sayisi)
    p_e            = safe_div(fiyat, eps) if eps and eps > 0 else 0.0
    eps_buyume     = pct_change(net_kar_y0, net_kar_y1)
    if temettu == 0:
        son_temettu_hisse = float(info.get("lastDividendValue") or 0)
        temettu = son_temettu_hisse * hisse_sayisi if son_temettu_hisse else 0

    # Beta
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            hist_raw = hisse.history(period="2y")["Close"].pct_change().dropna()
            hist_2y  = hist_raw
            hist_1y  = hist_raw.iloc[-252:] if len(hist_raw) >= 252 else hist_raw
    except Exception:
        hist_2y = hist_1y = pd.Series(dtype=float)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(calc_beta, ticker_symbol, hist_1y, "1y")
        f2 = ex.submit(calc_beta, ticker_symbol, hist_2y, "2y")
        beta_1y = f1.result()
        beta_2y = f2.result()

    # borsapy verileri ve sektörel karşılaştırma (paralel)
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_borsapy = ex.submit(_borsapy_verileri, ticker_symbol, info)
        sektor    = _sektor_bul(ticker_symbol) or info.get("sector", "")
        f_sektor  = ex.submit(_sektörel_karsilastirma, ticker_symbol, sektor)
        borsapy_ek  = f_borsapy.result()
        sektor_veri = f_sektor.result()

    # ─────────────────────────────────────────────
    #  SONUÇ DİKSİYONERİ
    # ─────────────────────────────────────────────
    s = {}

    # A. Genel Bilgiler
    s["Firma Sektörü"]       = sektor or info.get("sector", "-")
    s["Çalışan Sayısı"]      = info.get("fullTimeEmployees", "-")
    s["Para Birimi"]          = info.get("currency", "-")
    s["Borsa"]                = info.get("exchange", "-")
    s["Bilanço Dönemi"]      = bs.columns[0].strftime("%Y-%m") if not bs.empty else "-"
    s["Son Çeyrek Dönemi"]   = q_inc.columns[0].strftime("%Y-%m") if q_inc is not None and not q_inc.empty else "-"

    # B. Piyasa Verileri
    s["Fiyat"]                = fiyat
    s["Piyasa Değeri"]        = piyasa_degeri
    s["F/K (Günlük)"]         = round(float(info.get("trailingPE") or 0), 2)
    s["PD/DD (Günlük)"]       = round(float(info.get("priceToBook") or 0), 2)
    s["FD/FAVÖK (Günlük)"]    = round(float(info.get("enterpriseToEbitda") or 0), 2)
    s["BETA (yFinance)"]      = round(float(info.get("beta") or 0), 2)
    s["BETA (Manuel 1Y)"]     = beta_1y
    s["BETA (Manuel 2Y)"]     = beta_2y
    s["PEG Oranı (Günlük)"]   = round(float(info.get("pegRatio") or 0), 2)

    # borsapy: fiili dolaşım + yabancı oranı
    s["Fiili Dolaşım (%)"]    = borsapy_ek.get("Fiili Dolaşım (%)", "sektor_yukle.py çalıştırın")
    s["Yabancı Oranı (%)"]    = borsapy_ek.get("Yabancı Oranı (%)", "-")
    # Veri doğrulama sonucu
    if "⚠️ Veri Tutarsızlığı" in borsapy_ek:
        s["⚠️ Veri Tutarsızlığı"] = borsapy_ek["⚠️ Veri Tutarsızlığı"]
    elif "✅ Veri Doğrulaması" in borsapy_ek:
        s["✅ Veri Doğrulaması"]  = borsapy_ek["✅ Veri Doğrulaması"]

    # C. Değerleme (hesaplanan)
    s["F/K (Hesaplanan)"]     = p_e
    s["PD/DD (Hesaplanan)"]   = safe_div(fiyat, defter_hisse)
    s["F/S (Fiyat/Satış)"]    = safe_div(fiyat, satis_hisse)
    s["EV/EBITDA (Hesaplanan)"] = safe_div(kur_deg_y, ebitda)
    s["EV/EBIT"]              = safe_div(kur_deg_y, ebit)
    s["EV/Sales"]             = safe_div(kur_deg_y, satis_y0)
    s["PEG Oranı (Hesaplanan)"] = safe_div(p_e, eps_buyume) if eps_buyume > 0 else 0.0

    # D. Sektörel Karşılaştırma
    if sektor_veri:
        n = sektor_veri.get("_sektor_hisse_sayisi", 0)
        s[f"Sektör ({sektor}) — Hisse Sayısı"] = n
        for k, v in sektor_veri.items():
            if not k.startswith("_"):
                s[k] = v

    # E. Analist Hedefleri
    for k in ["Analist Hedef — Ort (TL)", "Analist Hedef — Med (TL)",
              "Analist Hedef — Min (TL)", "Analist Hedef — Maks (TL)", "Analist Sayısı"]:
        if k in borsapy_ek:
            s[k] = borsapy_ek[k]

    # F. Ana Ortaklar
    if "Ana Ortaklar" in borsapy_ek:
        s["Ana Ortaklar"] = borsapy_ek["Ana Ortaklar"]

    # G. Karlılık — Yıllık
    s["Net Kar Marjı — Yıllık (%)"]          = safe_div(net_kar_y0, satis_y0, multiply=100)
    s["Brüt Kar Marjı — Yıllık (%)"]         = safe_div(brut_kar_y0, satis_y0, multiply=100)
    s["İşletme Kar Marjı — Yıllık (%)"]      = safe_div(isletme_kari, satis_y0, multiply=100)
    s["FAVÖK Marjı — Yıllık (%)"]            = safe_div(ebitda, satis_y0, multiply=100)
    s["Özsermaye Karlılığı (ROE) — Yıllık"]  = safe_div(net_kar_y0, oz_sermaye_y0, multiply=100)
    s["Varlık Karlılığı (ROA) — Yıllık"]     = safe_div(net_kar_y0, varliklar_y0,  multiply=100)
    s["ROIC (%)"]                             = safe_div(nopat, yat_sermaye, multiply=100) if yat_sermaye > 0 else 0.0

    # H. Karlılık — Çeyreklik
    q_amortisman_duzeltme = q_amortisman if q_amortisman > 0 else (amortisman / 4)
    q_ebitda_q0_duz = q_ebit_q0 + q_amortisman_duzeltme
    s["Net Kar Marjı — Çeyreklik (%)"]        = safe_div(q_net_kar_q0, q_satis_q0, multiply=100)
    s["Brüt Kar Marjı — Çeyreklik (%)"]       = safe_div(q_brut_kar_q0, q_satis_q0, multiply=100)
    s["FAVÖK Marjı — Çeyreklik (%)"]          = safe_div(q_ebitda_q0_duz, q_satis_q0, multiply=100)
    s["Özsermaye Karlılığı — Çeyreklik (%)"]  = safe_div(q_net_kar_q0, q_oz_sermaye, multiply=100)

    # I. Büyüme
    s["Satış Büyümesi — Yıllık (%)"]          = pct_change(satis_y0, satis_y1)
    s["Net Kar Büyümesi — Yıllık (%)"]        = pct_change(net_kar_y0, net_kar_y1)
    s["EPS Büyümesi — Yıllık (%)"]            = eps_buyume
    s["Satış Büyümesi — QoQ (%)"]             = pct_change(q_satis_q0, q_satis_q1)
    s["Satış Büyümesi — YoY (%)"]             = pct_change(q_satis_q0, q_satis_q4)

    # J. Likidite
    s["Cari Oran"]                 = safe_div(donen, kisa_borc)
    s["Likidite Oranı (Hızlı)"]    = safe_div(donen - stok_y0, kisa_borc)
    s["Nakit Oranı"]               = safe_div(nakit, kisa_borc)

    # K. Borç / Kaldıraç
    faiz_geliri     = abs(get_val(inc, ["Interest Income", "Interest Income Non Operating", "Net Interest Income"], 0))
    net_faiz_gideri = faiz_gideri - faiz_geliri
    s["Borç / Özsermaye (D/E)"]        = safe_div(toplam_borc, oz_sermaye_y0)
    s["Finansal Borç / Özsermaye (%)"] = safe_div(toplam_borc, oz_sermaye_y0, multiply=100)
    s["Net Borç / FAVÖK"]              = safe_div(toplam_borc - nakit, ebitda)
    if net_faiz_gideri > 0:
        s["Faiz Karşılama Oranı"] = safe_div(ebit, net_faiz_gideri)
    elif faiz_gideri > 0:
        s["Faiz Karşılama Oranı"] = safe_div(ebit, faiz_gideri)
    else:
        s["Faiz Karşılama Oranı"] = 0.0
    s["Finansal Borç / Varlık (%)"] = safe_div(toplam_borc, varliklar_y0, multiply=100)

    # L. Faaliyet Etkinliği
    s["Varlık Devir Hızı"]  = safe_div(satis_y0, varliklar_y0)
    s["Stok Devir Hızı"]    = safe_div(cogs_y0,  stok_y0)
    s["Alacak Devir Hızı"]  = safe_div(satis_y0, alacak_y0)
    s["Stok Günü (DSI)"]    = safe_div(stok_y0,  cogs_y0,  multiply=365)
    s["Alacak Günü (DSO)"]  = safe_div(alacak_y0, satis_y0, multiply=365)

    # M. Nakit Akışı
    s["FCF (Serbest Nakit Akışı)"] = round(fcf, 0)
    s["FCF Getirisi (%)"]          = safe_div(fcf, piyasa_degeri, multiply=100)
    s["FCF / Net Kar"]             = safe_div(fcf, net_kar_y0)
    s["Temettü Verimi (%)"]        = round(float(info.get("dividendYield") or 0) * 100, 2)
    s["Temettü Ödeme Oranı (%)"]   = safe_div(temettu, net_kar_y0, multiply=100)

    # N. Ham Referans Değerler
    s["_Satış — Yıllık"]       = round(satis_y0, 0)
    s["_Net Kar — Yıllık"]     = round(net_kar_y0, 0)
    s["_FAVÖK — Yıllık"]       = round(ebitda, 0)
    s["_İşletme Nakit Akışı"]  = round(op_nakit, 0)
    s["_CapEx"]                = round(capex, 0)
    s["_FCF"]                  = round(fcf, 0)
    s["_Sektör"]               = sektor

    return s


if __name__ == "__main__":
    from datetime import datetime
    ticker = "ASELS.IS"
    print(f"\n{'='*55}\n  {ticker} — TEMEL ANALİZ\n  {datetime.now():%d.%m.%Y %H:%M}\n{'='*55}")
    sonuc = temel_analiz_yap(ticker)
    for k, v in sonuc.items():
        if not k.startswith("_"):
            print(f"  {k:<45}: {v}")
