import yfinance as yf
import pandas as pd
import numpy as np


# ─────────────────────────────────────────────
#  PINE SCRIPT MATEMATİKSEL FONKSİYONLARI
# ─────────────────────────────────────────────

def rma(series: pd.Series, length: int) -> pd.Series:
    """
    Pine Script ta.rma → Wilder's Moving Average.
    EWM alpha = 1/length, adjust=False ile birebir eşleşir.
    """
    return series.ewm(alpha=1 / length, adjust=False).mean()


def wma(series: pd.Series, length: int) -> pd.Series:
    """
    Pine Script ta.wma → Ağırlıklı Hareketli Ortalama.
    Her bar için lineer ağırlık: 1, 2, ... length
    """
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


# ─────────────────────────────────────────────
#  ANA FONKSİYON
# ─────────────────────────────────────────────

def teknik_analiz_yap(ticker_symbol: str) -> dict:
    hisse = yf.Ticker(ticker_symbol)
    df = hisse.history(period="3y")   # 610 bar için 3 yıl yeterli

    if df.empty or len(df) < 20:
        return {"Hata": "Yeterli fiyat geçmişi yok."}

    c = df["Close"]
    h = df["High"]
    l = df["Low"]
    v = df["Volume"]
    delta = c.diff()

    s = {}
    s["Güncel Fiyat"] = round(c.iloc[-1], 2)

    # ── 1. RSI (Pine Script ta.rma birebir) ──────────────────────────────────
    up   = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    rs   = rma(up, 14) / rma(down, 14)
    rsi  = 100 - (100 / (1 + rs))
    rsi_sma = rsi.rolling(14).mean()
    s["RSI (14)"] = f"{rsi.iloc[-1]:.2f} (Hareketli Ort: {rsi_sma.iloc[-1]:.2f})"

    # ── 2. Stoch RSI (K=3, D=3 SMA — Pine Script varsayılanı) ───────────────
    rsi_ll  = rsi.rolling(14).min()
    rsi_hh  = rsi.rolling(14).max()
    stoch   = 100 * (rsi - rsi_ll) / (rsi_hh - rsi_ll)
    k_line  = stoch.rolling(3).mean()
    d_line  = k_line.rolling(3).mean()
    s["Stoch RSI (K / D)"] = f"{k_line.iloc[-1]:.2f} / {d_line.iloc[-1]:.2f}"

    # ── 3. Stokastik Momentum Index (SMI) ────────────────────────────────────
    hh_10     = h.rolling(10).max()
    ll_10     = l.rolling(10).min()
    hl_range  = hh_10 - ll_10
    rel_range = c - (hh_10 + ll_10) / 2
    ema1_rel  = rel_range.ewm(span=3, adjust=False).mean()
    ema2_rel  = ema1_rel.ewm(span=3, adjust=False).mean()
    ema1_hl   = hl_range.ewm(span=3, adjust=False).mean()
    ema2_hl   = ema1_hl.ewm(span=3, adjust=False).mean()
    smi       = 200 * (ema2_rel / ema2_hl.replace(0, np.nan))  # sıfıra bölünmeyi önle
    s["SMI (Stokastik Momentum)"] = round(smi.iloc[-1], 2)

    # ── 4. MACD (12, 26, 9 EMA — Pine Script varsayılanı) ───────────────────
    ema12  = c.ewm(span=12, adjust=False).mean()
    ema26  = c.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    s["MACD (12,26,9)"] = (
        f"Hat: {macd.iloc[-1]:.2f} | "
        f"Sinyal: {signal.iloc[-1]:.2f} | "
        f"Histogram: {hist.iloc[-1]:.2f}"
    )

    # ── 5. OBV (On-Balance Volume) ───────────────────────────────────────────
    obv     = (np.sign(delta) * v).fillna(0).cumsum()
    obv_sma = obv.rolling(14).mean()
    s["OBV"] = f"{obv.iloc[-1]:,.0f} (Ort: {obv_sma.iloc[-1]:,.0f})"

    # ── 6. CCI (Pine Script: (src - sma) / (0.015 * mad)) ───────────────────
    tp     = (h + l + c) / 3
    sma_tp = tp.rolling(20).mean()
    mad    = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    cci    = (tp - sma_tp) / (0.015 * mad)
    s["CCI (20)"] = round(cci.iloc[-1], 2)

    # ── 7. ATR (Pine Script ta.rma birebir) ──────────────────────────────────
    tr1 = h - l
    tr2 = (h - c.shift(1)).abs()
    tr3 = (l - c.shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = rma(tr, 14)
    s["ATR (14) Volatilite"] = round(atr.iloc[-1], 2)

    # ── 8. ADX / DMI (+DI, -DI) ──────────────────────────────────────────────
    up_move   = h.diff()
    down_move = (-l.diff())
    plus_dm   = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm  = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_safe  = atr.replace(0, np.nan)
    plus_di   = 100 * rma(pd.Series(plus_dm,  index=c.index), 14) / atr_safe
    minus_di  = 100 * rma(pd.Series(minus_dm, index=c.index), 14) / atr_safe
    di_sum    = (plus_di + minus_di).replace(0, np.nan)
    dx        = 100 * (plus_di - minus_di).abs() / di_sum
    adx       = rma(dx, 14)
    s["ADX (14) Trend Gücü"] = (
        f"{adx.iloc[-1]:.2f} "
        f"(+DI: {plus_di.iloc[-1]:.2f} | -DI: {minus_di.iloc[-1]:.2f})"
    )

    # ── 9. CMF (Chaikin Money Flow) ───────────────────────────────────────────
    hl_diff = (h - l).replace(0, np.nan)
    mfm     = (2 * c - l - h) / hl_diff   # Money Flow Multiplier
    mfv     = mfm * v                      # Money Flow Volume
    cmf     = mfv.rolling(20).sum() / v.rolling(20).sum()
    s["CMF (20) Para Akışı"] = round(cmf.iloc[-1], 2)

    # ── 10. Bollinger Bantları (Pine Script: ddof=0) ──────────────────────────
    bb_basis = c.rolling(20).mean()
    bb_dev   = 2 * c.rolling(20).std(ddof=0)
    s["Bollinger Bantları"] = (
        f"Alt: {(bb_basis - bb_dev).iloc[-1]:.2f} | "
        f"Orta: {bb_basis.iloc[-1]:.2f} | "
        f"Üst: {(bb_basis + bb_dev).iloc[-1]:.2f}"
    )

    # Bollinger Band Genişliği ve %B (ekstra sinyal)
    bb_width = (bb_dev * 2) / bb_basis * 100
    bb_pct_b = (c - (bb_basis - bb_dev)) / (bb_dev * 2)
    s["BB Genişliği (%)"]   = round(bb_width.iloc[-1], 2)
    s["BB %B"]              = round(bb_pct_b.iloc[-1], 2)

    # ── 11. Ichimoku Bulutu (9, 26, 52) ──────────────────────────────────────
    tenkan   = (h.rolling(9).max()  + l.rolling(9).min())  / 2
    kijun    = (h.rolling(26).max() + l.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    chikou   = c.shift(-26)

    # Bulutun rengi: Senkou A > Senkou B → Yeşil (yükselen), aksi → Kırmızı
    bulut = "Yeşil (Yükselen)" if senkou_a.iloc[-1] > senkou_b.iloc[-1] else "Kırmızı (Düşen)"
    s["Ichimoku (Tenkan/Kijun)"] = f"{tenkan.iloc[-1]:.2f} / {kijun.iloc[-1]:.2f}"
    s["Ichimoku Bulut"]          = bulut

    # ── 12. Momentum ─────────────────────────────────────────────────────────
    mom = c - c.shift(10)
    s["Momentum (10)"] = round(mom.iloc[-1], 2)

    # ── 13. Göreceli Hacim (RVOL) ─────────────────────────────────────────────
    # Pine Script: volume / ta.sma(volume, 10)[1]
    # shift(1) → mevcut çubuğu hariç tutar, son 10 çubuğun SMA'sını alır
    avg_vol_10 = v.shift(1).rolling(10).mean()
    rvol = v / avg_vol_10
    s["Göreceli Hacim (RVOL)"] = round(rvol.iloc[-1], 2)

    # ── 15. Pivot Noktaları (Geleneksel — önceki bar verisiyle) ──────────────
    prev_h = h.iloc[-2]
    prev_l = l.iloc[-2]
    prev_c = c.iloc[-2]
    pivot  = (prev_h + prev_l + prev_c) / 3
    r1 = 2 * pivot - prev_l
    s1 = 2 * pivot - prev_h
    r2 = pivot + (prev_h - prev_l)
    s2 = pivot - (prev_h - prev_l)
    r3 = prev_h + 2 * (pivot - prev_l)
    s3 = prev_l - 2 * (prev_h - pivot)
    s["Pivot (Geleneksel)"] = (
        f"P: {pivot:.2f} | "
        f"R1: {r1:.2f} | S1: {s1:.2f} | "
        f"R2: {r2:.2f} | S2: {s2:.2f} | "
        f"R3: {r3:.2f} | S3: {s3:.2f}"
    )

    # ── 16. Hareketli Ortalamalar (SMA, EMA, WMA) ────────────────────────────
    ma_periodlari = [5, 8, 13, 20, 21, 34, 50, 55, 89, 100, 144, 233, 377, 610]
    sma_list, ema_list, wma_list = [], [], []

    for p in ma_periodlari:
        if len(c) >= p:
            sma_val = c.rolling(p).mean().iloc[-1]
            ema_val = c.ewm(span=p, adjust=False).mean().iloc[-1]
            wma_val = wma(c, p).iloc[-1]
            sma_list.append(f"{p}g:{sma_val:.1f}")
            ema_list.append(f"{p}g:{ema_val:.1f}")
            wma_list.append(f"{p}g:{wma_val:.1f}")
        else:
            sma_list.append(f"{p}g:-")
            ema_list.append(f"{p}g:-")
            wma_list.append(f"{p}g:-")

    s["SMA (Basit)"]     = " | ".join(sma_list)
    s["EMA (Üstel)"]     = " | ".join(ema_list)
    s["WMA (Ağırlıklı)"] = " | ".join(wma_list)

    return s
