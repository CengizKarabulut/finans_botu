import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed


# ─────────────────────────────────────────────
#  YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def get_val(df: pd.DataFrame, row_names: list, col_index: int = 0) -> float:
    """DataFrame'den güvenli değer çekme. Bulunamazsa 0.0 döner."""
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
    """Sıfıra bölme korumalı bölme. Sonucu 2 ondalıkla döner."""
    try:
        if payda and payda != 0:
            return round((pay / payda) * multiply, 2)
    except Exception:
        pass
    return fallback


def pct_change(yeni, eski) -> float:
    """
    Yüzde değişim hesabı.
    Negatif tabanlarda da (zarar→kâr geçişi) doğru sonuç verir.
    """
    if eski and eski != 0:
        return round((yeni - eski) / abs(eski) * 100, 2)
    return 0.0


def calc_beta(ticker_symbol: str, stock_returns: pd.Series, period: str = "1y") -> float:
    """
    Manuel beta: Cov(hisse, endeks) / Var(endeks)
    stock_returns: önceden hesaplanmış hisse günlük getirileri (history zaten çekildi)
    Endeks verisini bu fonksiyon çeker — paralel çağrılmaya uygundur.
    """
    try:
        benchmark = "XU100.IS" if ticker_symbol.upper().endswith(".IS") else "^GSPC"
        m = yf.Ticker(benchmark).history(period=period)["Close"].pct_change().dropna()
        df = pd.concat([stock_returns, m], axis=1, join="inner")
        df.columns = ["Stock", "Market"]
        cov = df.cov().iloc[0, 1]
        var = df["Market"].var()
        return round(cov / var, 3) if var > 0 else 0.0
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
#  ANA FONKSİYON
# ─────────────────────────────────────────────

def temel_analiz_yap(ticker_symbol: str) -> dict:
    hisse = yf.Ticker(ticker_symbol)

    # ── Paralel Veri Çekimi ───────────────────────────────────────────────────
    # yFinance her property çağrısında ayrı HTTP isteği atar.
    # ThreadPoolExecutor ile hepsini aynı anda başlatıyoruz.
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

    # ── Yıllık Gelir Tablosu ──────────────────────────────────────────────────
    satis_y0       = get_val(inc, ["Total Revenue", "Operating Revenue"], 0)
    satis_y1       = get_val(inc, ["Total Revenue", "Operating Revenue"], 1)

    net_kar_y0     = get_val(inc, ["Net Income"], 0)
    net_kar_y1     = get_val(inc, ["Net Income"], 1)

    cogs_y0        = get_val(inc, ["Cost Of Revenue"], 0)
    brut_kar_y0    = get_val(inc, ["Gross Profit"], 0) or (satis_y0 - cogs_y0)

    isletme_kari   = get_val(inc, ["Operating Income",
                                    "Total Operating Income As Reported"], 0)
    ebit           = get_val(inc, ["EBIT"], 0) or isletme_kari
    faiz_gideri    = abs(get_val(inc, ["Interest Expense",
                                        "Interest Expense Non Operating"], 0))
    vergi_gideri   = abs(get_val(inc, ["Tax Provision", "Income Tax Expense"], 0))

    # ── Yıllık Nakit Akışı ────────────────────────────────────────────────────
    amortisman     = get_val(cf, ["Depreciation And Amortization",
                                   "Depreciation Amortization Depletion"], 0)
    op_nakit       = get_val(cf, ["Operating Cash Flow"], 0)
    capex          = abs(get_val(cf, ["Capital Expenditure",
                                       "Purchase Of Plant And Equipment",
                                       "Purchases Of Property Plant And Equipment"], 0))
    temettu        = abs(get_val(cf, ["Cash Dividends Paid", "Common Stock Dividend Paid"], 0))

    # EBITDA: info varsa kullan, yoksa EBIT + Amortisman
    ebitda         = float(info.get("ebitda") or 0) or (ebit + amortisman)

    # ── Yıllık Bilanço ────────────────────────────────────────────────────────
    oz_sermaye_y0  = get_val(bs, ["Stockholders Equity",
                                   "Total Equity Gross Minority Interest"], 0)
    oz_sermaye_y1  = get_val(bs, ["Stockholders Equity",
                                   "Total Equity Gross Minority Interest"], 1)
    ort_oz_sermaye = (oz_sermaye_y0 + oz_sermaye_y1) / 2 if oz_sermaye_y1 != 0 else oz_sermaye_y0

    varliklar_y0   = get_val(bs, ["Total Assets"], 0)
    varliklar_y1   = get_val(bs, ["Total Assets"], 1)
    ort_varliklar  = (varliklar_y0 + varliklar_y1) / 2 if varliklar_y1 != 0 else varliklar_y0

    donen          = get_val(bs, ["Current Assets", "Total Current Assets"], 0)
    kisa_borc      = get_val(bs, ["Current Liabilities", "Total Current Liabilities Net Minority Interest"], 0)
    stok_y0        = get_val(bs, ["Inventory", "Inventories", "Finished Goods"], 0)
    stok_y1        = get_val(bs, ["Inventory", "Inventories", "Finished Goods"], 1)
    ort_stok       = (stok_y0 + stok_y1) / 2 if stok_y1 != 0 else stok_y0
    alacak_y0      = get_val(bs, ["Accounts Receivable", "Net Receivables",
                                   "Receivables", "Trade And Other Receivables Non Current"], 0)
    alacak_y1      = get_val(bs, ["Accounts Receivable", "Net Receivables",
                                   "Receivables", "Trade And Other Receivables Non Current"], 1)
    ort_alacak     = (alacak_y0 + alacak_y1) / 2 if alacak_y1 != 0 else alacak_y0

    nakit          = get_val(bs, ["Cash And Cash Equivalents",
                                   "Cash Cash Equivalents And Short Term Investments",
                                   "Cash And Short Term Investments"], 0)
    toplam_borc    = get_val(bs, ["Total Debt", "Long Term Debt And Capital Lease Obligation"], 0)
    uzun_v_borc    = get_val(bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 0)

    # ── Çeyreklik Veriler ─────────────────────────────────────────────────────
    # BIST'te son çeyrek boş gelebilir; dolu olan ilk çeyreği bul
    def _q_ilk_dolu(df_q, row_names):
        """Son 4 çeyrek içinde ilk dolu değeri döner (col_index 0-3 dener)."""
        for i in range(4):
            v = get_val(df_q, row_names, i)
            if v != 0:
                return v, i
        return 0.0, 0

    q_satis_q0, q0_idx = _q_ilk_dolu(q_inc, ["Total Revenue", "Operating Revenue"])
    q_satis_q1         = get_val(q_inc, ["Total Revenue", "Operating Revenue"], q0_idx + 1)
    q_satis_q4         = get_val(q_inc, ["Total Revenue", "Operating Revenue"], q0_idx + 4)

    q_net_kar_q0   = get_val(q_inc, ["Net Income"], q0_idx)
    q_cogs_q0      = get_val(q_inc, ["Cost Of Revenue"], q0_idx)
    q_brut_kar_q0  = get_val(q_inc, ["Gross Profit"], q0_idx) or (q_satis_q0 - q_cogs_q0)
    q_ebit_q0      = get_val(q_inc, ["EBIT", "Operating Income"], q0_idx)
    q_amortisman   = get_val(q_cf,  ["Depreciation And Amortization"], q0_idx)
    q_ebitda_q0    = q_ebit_q0 + q_amortisman
    q_oz_sermaye   = get_val(q_bs,  ["Stockholders Equity",
                                      "Total Equity Gross Minority Interest"], 0)

    # ── Piyasa Verileri ───────────────────────────────────────────────────────
    fiyat          = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
    piyasa_degeri  = float(info.get("marketCap") or 0)
    hisse_sayisi   = float(info.get("sharesOutstanding") or 1)
    kur_deg_y      = float(info.get("enterpriseValue") or 0)
    eps            = float(info.get("trailingEps") or 0) or safe_div(net_kar_y0, hisse_sayisi)
    float_shares   = float(info.get("floatShares") or 0)

    # ── Türetilmiş Değerler ───────────────────────────────────────────────────
    vergi_orani    = safe_div(vergi_gideri, ebit) if ebit > 0 else 0.20
    yat_sermaye    = toplam_borc + oz_sermaye_y0 - nakit   # Invested Capital
    nopat          = ebit * (1 - vergi_orani)              # Net Operating Profit After Tax
    fcf            = op_nakit - capex
    defter_hisse   = safe_div(oz_sermaye_y0, hisse_sayisi)
    satis_hisse    = safe_div(satis_y0, hisse_sayisi)
    p_e            = safe_div(fiyat, eps) if eps and eps > 0 else 0.0
    eps_buyume     = pct_change(net_kar_y0, net_kar_y1)
    # Temettü: BIST'te Cash Dividends Paid çekilemeyebilir → hisse başı * adet
    if temettu == 0:
        son_temettu_hisse = float(info.get("lastDividendValue") or 0)
        temettu = son_temettu_hisse * hisse_sayisi if son_temettu_hisse else 0

    # ── Beta: hisse geçmişini tek seferinde çek, 1Y ve 2Y endeks paralel ─────
    try:
        hist_2y        = hisse.history(period="2y")["Close"].pct_change().dropna()
        hist_1y        = hist_2y.last("365D")
    except Exception:
        hist_2y = hist_1y = pd.Series(dtype=float)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(calc_beta, ticker_symbol, hist_1y, "1y")
        f2 = ex.submit(calc_beta, ticker_symbol, hist_2y, "2y")
        beta_1y = f1.result()
        beta_2y = f2.result()

    # ─────────────────────────────────────────────
    #  SONUÇ DİKSİYONERİ
    # ─────────────────────────────────────────────
    s = {}

    # A. Genel Bilgiler
    s["Firma Sektörü"]          = info.get("sector", "-")
    s["Çalışan Sayısı"]         = info.get("fullTimeEmployees", "-")
    s["Para Birimi"]             = info.get("currency", "-")
    s["Borsa"]                   = info.get("exchange", "-")
    s["Bilanço Dönemi"]         = bs.columns[0].strftime("%Y-%m") if not bs.empty else "-"
    s["Son Çeyrek Dönemi"]      = q_inc.columns[0].strftime("%Y-%m") if q_inc is not None and not q_inc.empty else "-"

    # B. Günlük Piyasa Verileri (doğrudan info'dan)
    s["Fiyat"]                   = fiyat
    s["Piyasa Değeri"]           = piyasa_degeri
    s["F/K (Günlük)"]            = round(float(info.get("trailingPE") or 0), 2)
    s["PD/DD (Günlük)"]          = round(float(info.get("priceToBook") or 0), 2)
    s["FD/FAVÖK (Günlük)"]       = round(float(info.get("enterpriseToEbitda") or 0), 2)
    s["BETA (yFinance)"]         = round(float(info.get("beta") or 0), 2)
    s["BETA (Manuel 1Y)"]        = beta_1y
    s["BETA (Manuel 2Y)"]        = beta_2y
    s["PEG Oranı (Günlük)"]      = round(float(info.get("pegRatio") or 0), 2)
    s["Fiili Dolaşım (%)"]       = safe_div(float_shares, hisse_sayisi, multiply=100) if float_shares else "-"

    # C. Değerleme (hesaplanan)
    s["F/K (Hesaplanan)"]        = p_e
    s["PD/DD (Hesaplanan)"]      = safe_div(fiyat, defter_hisse)
    s["F/S (Fiyat/Satış)"]       = safe_div(fiyat, satis_hisse)
    s["EV/EBITDA (Hesaplanan)"]  = safe_div(kur_deg_y, ebitda)
    s["EV/EBIT"]                 = safe_div(kur_deg_y, ebit)
    s["EV/Sales"]                = safe_div(kur_deg_y, satis_y0)
    s["PEG Oranı (Hesaplanan)"]  = safe_div(p_e, eps_buyume) if eps_buyume > 0 else 0.0

    # D. Karlılık — Yıllık
    s["Net Kar Marjı — Yıllık (%)"]         = safe_div(net_kar_y0, satis_y0, multiply=100)
    s["Brüt Kar Marjı — Yıllık (%)"]        = safe_div(brut_kar_y0, satis_y0, multiply=100)
    s["İşletme Kar Marjı — Yıllık (%)"]     = safe_div(isletme_kari, satis_y0, multiply=100)
    s["FAVÖK Marjı — Yıllık (%)"]           = safe_div(ebitda, satis_y0, multiply=100)
    s["Özsermaye Karlılığı (ROE) — Yıllık"] = safe_div(net_kar_y0, ort_oz_sermaye, multiply=100)
    s["Varlık Karlılığı (ROA) — Yıllık"]    = safe_div(net_kar_y0, ort_varliklar, multiply=100)
    s["ROIC (%)"]                            = safe_div(nopat, yat_sermaye, multiply=100) if yat_sermaye > 0 else 0.0

    # E. Karlılık — Çeyreklik
    s["Net Kar Marjı — Çeyreklik (%)"]       = safe_div(q_net_kar_q0, q_satis_q0, multiply=100)
    s["Brüt Kar Marjı — Çeyreklik (%)"]      = safe_div(q_brut_kar_q0, q_satis_q0, multiply=100)
    s["FAVÖK Marjı — Çeyreklik (%)"]         = safe_div(q_ebitda_q0, q_satis_q0, multiply=100)
    s["Özsermaye Karlılığı — Çeyreklik (%)"] = safe_div(q_net_kar_q0, q_oz_sermaye, multiply=100)

    # F. Büyüme
    s["Satış Büyümesi — Yıllık (%)"]         = pct_change(satis_y0, satis_y1)
    s["Net Kar Büyümesi — Yıllık (%)"]       = pct_change(net_kar_y0, net_kar_y1)
    s["EPS Büyümesi — Yıllık (%)"]           = eps_buyume
    s["Satış Büyümesi — QoQ (%)"]            = pct_change(q_satis_q0, q_satis_q1)
    s["Satış Büyümesi — YoY (%)"]            = pct_change(q_satis_q0, q_satis_q4)

    # G. Likidite
    s["Cari Oran"]                  = safe_div(donen, kisa_borc)
    s["Likidite Oranı (Hızlı)"]     = safe_div(donen - stok_y0, kisa_borc)
    s["Nakit Oranı"]                = safe_div(nakit, kisa_borc)

    # H. Borç / Kaldıraç
    s["Borç / Özsermaye (D/E)"]     = safe_div(toplam_borc, oz_sermaye_y0)
    s["Net Borç / FAVÖK"]           = safe_div(toplam_borc - nakit, ebitda)
    s["Faiz Karşılama Oranı"]       = safe_div(ebit, faiz_gideri)
    s["Finansal Borç / Varlık (%)"] = safe_div(toplam_borc, varliklar_y0, multiply=100)

    # I. Faaliyet Etkinliği
    s["Varlık Devir Hızı"]          = safe_div(satis_y0, ort_varliklar)
    s["Stok Devir Hızı"]            = safe_div(cogs_y0, ort_stok)
    s["Alacak Devir Hızı"]          = safe_div(satis_y0, ort_alacak)
    s["Stok Günü (DSI)"]            = safe_div(ort_stok, cogs_y0, multiply=365)
    s["Alacak Günü (DSO)"]          = safe_div(ort_alacak, satis_y0, multiply=365)

    # J. Nakit Akışı
    s["FCF (Serbest Nakit Akışı)"]  = round(fcf, 0)
    s["FCF Getirisi (%)"]           = safe_div(fcf, piyasa_degeri, multiply=100)
    s["FCF / Net Kar"]              = safe_div(fcf, net_kar_y0)
    s["Temettü Verimi (%)"]         = round(float(info.get("dividendYield") or 0) * 100, 2)
    s["Temettü Ödeme Oranı (%)"]    = safe_div(temettu, net_kar_y0, multiply=100)

    # K. Ham Referans Değerler (başında _ — bot/rapor bunları filtreler)
    s["_Satış — Yıllık"]            = round(satis_y0, 0)
    s["_Net Kar — Yıllık"]          = round(net_kar_y0, 0)
    s["_FAVÖK — Yıllık"]            = round(ebitda, 0)
    s["_İşletme Nakit Akışı"]       = round(op_nakit, 0)
    s["_CapEx"]                     = round(capex, 0)
    s["_FCF"]                       = round(fcf, 0)

    return s


# ─────────────────────────────────────────────
#  YAZICI FONKSİYON (Terminal / Debug)
# ─────────────────────────────────────────────

def yazdir(ticker_symbol: str):
    from datetime import datetime
    print(f"\n{'═'*55}")
    print(f"  {ticker_symbol.upper()} — TEMEL ANALİZ RAPORU")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"{'═'*55}")

    sonuclar = temel_analiz_yap(ticker_symbol)

    if "Hata" in sonuclar:
        print(f"  ❌ {sonuclar['Hata']}")
        return

    GRUPLAR = {
        "A. Genel Bilgiler":        ["Firma Sektörü", "Çalışan Sayısı", "Bilanço Dönemi",
                                     "Son Çeyrek Dönemi", "Para Birimi", "Borsa"],
        "B. Piyasa Verileri":       ["Fiyat", "Piyasa Değeri",
                                     "F/K (Günlük)", "PD/DD (Günlük)", "FD/FAVÖK (Günlük)",
                                     "BETA (yFinance)", "BETA (Manuel 1Y)", "BETA (Manuel 2Y)",
                                     "PEG Oranı (Günlük)", "Fiili Dolaşım (%)"],
        "C. Değerleme":             ["F/K (Hesaplanan)", "PD/DD (Hesaplanan)", "F/S (Fiyat/Satış)",
                                     "EV/EBITDA (Hesaplanan)", "EV/EBIT", "EV/Sales",
                                     "PEG Oranı (Hesaplanan)"],
        "D. Karlılık — Yıllık":     ["Net Kar Marjı — Yıllık (%)", "Brüt Kar Marjı — Yıllık (%)",
                                     "İşletme Kar Marjı — Yıllık (%)", "FAVÖK Marjı — Yıllık (%)",
                                     "Özsermaye Karlılığı (ROE) — Yıllık",
                                     "Varlık Karlılığı (ROA) — Yıllık", "ROIC (%)"],
        "E. Karlılık — Çeyreklik":  ["Net Kar Marjı — Çeyreklik (%)", "Brüt Kar Marjı — Çeyreklik (%)",
                                     "FAVÖK Marjı — Çeyreklik (%)",
                                     "Özsermaye Karlılığı — Çeyreklik (%)"],
        "F. Büyüme":                ["Satış Büyümesi — Yıllık (%)", "Net Kar Büyümesi — Yıllık (%)",
                                     "EPS Büyümesi — Yıllık (%)",
                                     "Satış Büyümesi — QoQ (%)", "Satış Büyümesi — YoY (%)"],
        "G. Likidite":              ["Cari Oran", "Likidite Oranı (Hızlı)", "Nakit Oranı"],
        "H. Borç / Kaldıraç":       ["Borç / Özsermaye (D/E)", "Net Borç / FAVÖK",
                                     "Faiz Karşılama Oranı", "Finansal Borç / Varlık (%)"],
        "I. Faaliyet Etkinliği":    ["Varlık Devir Hızı", "Stok Devir Hızı", "Alacak Devir Hızı",
                                     "Stok Günü (DSI)", "Alacak Günü (DSO)"],
        "J. Nakit Akışı":           ["FCF (Serbest Nakit Akışı)", "FCF Getirisi (%)", "FCF / Net Kar",
                                     "Temettü Verimi (%)", "Temettü Ödeme Oranı (%)"],
        "K. Ham Değerler":          ["_Satış — Yıllık", "_Net Kar — Yıllık", "_FAVÖK — Yıllık",
                                     "_İşletme Nakit Akışı", "_CapEx", "_FCF"],
    }

    for grup_adi, anahtarlar in GRUPLAR.items():
        print(f"\n  ── {grup_adi} {'─'*(45 - len(grup_adi))}")
        for k in anahtarlar:
            v = sonuclar.get(k, "-")
            etiket = k.lstrip("_")
            if isinstance(v, float):
                print(f"    {etiket:<42}: {v:>10.2f}")
            elif isinstance(v, int) and abs(v) > 1_000_000:
                print(f"    {etiket:<42}: {v:>15,.0f}")
            else:
                print(f"    {etiket:<42}: {str(v):>10}")

    print(f"\n{'═'*55}\n")


if __name__ == "__main__":
    yazdir("ASELS.IS")
    # yazdir("AAPL")
