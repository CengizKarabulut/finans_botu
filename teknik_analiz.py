import yfinance as yf
import pandas as pd
import numpy as np


def rma(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1 / length, adjust=False).mean()

def wma(series: pd.Series, length: int) -> pd.Series:
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def _pivot_low(series, left, right):
    result = pd.Series(np.nan, index=series.index)
    for i in range(left, len(series) - right):
        val = series.iloc[i]
        if val == series.iloc[i - left: i + right + 1].min():
            result.iloc[i] = val
    return result

def _pivot_high(series, left, right):
    result = pd.Series(np.nan, index=series.index)
    for i in range(left, len(series) - right):
        val = series.iloc[i]
        if val == series.iloc[i - left: i + right + 1].max():
            result.iloc[i] = val
    return result

def _rsi_divergence(rsi, price, lookback_left=5, lookback_right=5, range_lower=5, range_upper=60):
    pl = _pivot_low(rsi,  lookback_left, lookback_right)
    ph = _pivot_high(rsi, lookback_left, lookback_right)
    n = len(rsi)
    bull_divs, bear_divs = [], []
    for i in range(lookback_right, n):
        if not np.isnan(pl.iloc[i]):
            prev_idx = None
            for j in range(i - range_lower, max(i - range_upper, 0) - 1, -1):
                if j >= 0 and not np.isnan(pl.iloc[j]):
                    prev_idx = j; break
            if prev_idx is not None:
                if rsi.iloc[i] > rsi.iloc[prev_idx] and price.iloc[i] < price.iloc[prev_idx]:
                    bull_divs.append(i)
        if not np.isnan(ph.iloc[i]):
            prev_idx = None
            for j in range(i - range_lower, max(i - range_upper, 0) - 1, -1):
                if j >= 0 and not np.isnan(ph.iloc[j]):
                    prev_idx = j; break
            if prev_idx is not None:
                if rsi.iloc[i] < rsi.iloc[prev_idx] and price.iloc[i] > price.iloc[prev_idx]:
                    bear_divs.append(i)
    son_bull = (n - 1 - bull_divs[-1] - lookback_right) if bull_divs else None
    son_bear = (n - 1 - bear_divs[-1] - lookback_right) if bear_divs else None
    return {"bullish_bars_ago": son_bull, "bearish_bars_ago": son_bear}

def teknik_analiz_yap(ticker_symbol: str) -> dict:
    hisse = yf.Ticker(ticker_symbol)
    df    = hisse.history(period="3y")
    if df.empty or len(df) < 20:
        return {"Hata": "Yeterli fiyat geçmişi yok."}

    c = df["Close"]; h = df["High"]; l = df["Low"]; v = df["Volume"]
    delta = c.diff()
    s = {}
    s["Güncel Fiyat"] = round(c.iloc[-1], 2)

    # 1. RSI — Pine Script birebir (edge case: up==0 → 0, down==0 → 100)
    up = delta.clip(lower=0); down = (-delta).clip(lower=0)
    rma_up = rma(up, 14); rma_down = rma(down, 14)
    rsi_arr = np.where(rma_down == 0, 100, np.where(rma_up == 0, 0, 100 - (100 / (1 + rma_up / rma_down))))
    rsi = pd.Series(rsi_arr, index=c.index)
    rsi_sma = rsi.rolling(14).mean()
    s["RSI (14)"] = f"{rsi.iloc[-1]:.2f} (Hareketli Ort: {rsi_sma.iloc[-1]:.2f})"

    # RSI Divergence
    try:
        div = _rsi_divergence(rsi, c)
        bull_ago = div["bullish_bars_ago"]; bear_ago = div["bearish_bars_ago"]
        if bull_ago is not None and (bear_ago is None or bull_ago <= bear_ago):
            s["RSI Divergence"] = f"Boğa (Bullish) — {bull_ago} bar önce"
        elif bear_ago is not None:
            s["RSI Divergence"] = f"Ayı (Bearish) — {bear_ago} bar önce"
        else:
            s["RSI Divergence"] = "Yok"
    except Exception:
        s["RSI Divergence"] = "Hesaplanamadı"

    # 2. Stoch RSI
    rsi_ll = rsi.rolling(14).min(); rsi_hh = rsi.rolling(14).max()
    stoch  = 100 * (rsi - rsi_ll) / (rsi_hh - rsi_ll).replace(0, np.nan)
    k_line = stoch.rolling(3).mean(); d_line = k_line.rolling(3).mean()
    s["Stoch RSI (K / D)"] = f"{k_line.iloc[-1]:.2f} / {d_line.iloc[-1]:.2f}"

    # 3. SMI
    hh_10 = h.rolling(10).max(); ll_10 = l.rolling(10).min()
    hl_range = hh_10 - ll_10; rel_range = c - (hh_10 + ll_10) / 2
    ema2_rel = rel_range.ewm(span=3,adjust=False).mean().ewm(span=3,adjust=False).mean()
    ema2_hl  = hl_range.ewm(span=3,adjust=False).mean().ewm(span=3,adjust=False).mean()
    smi = 200 * (ema2_rel / ema2_hl.replace(0, np.nan))
    s["SMI (Stokastik Momentum)"] = round(smi.iloc[-1], 2)

    # 4. MACD
    macd = c.ewm(span=12,adjust=False).mean() - c.ewm(span=26,adjust=False).mean()
    signal = macd.ewm(span=9,adjust=False).mean()
    s["MACD (12,26,9)"] = f"Hat: {macd.iloc[-1]:.2f} | Sinyal: {signal.iloc[-1]:.2f} | Histogram: {(macd-signal).iloc[-1]:.2f}"

    # 5. OBV — Pine Script birebir: ta.cum(math.sign(ta.change(close)) * volume)
    # DÜZELTME: fillna(0) yerine ilk bar sign=0 olarak ayarlandı.
    # Mutlak değer önemli değil, trend yönü önemli.
    obv_sign = np.sign(delta)
    obv_sign.iloc[0] = 0  # ilk bar NaN → 0 (Pine ile aynı davranış)
    obv = (obv_sign * v).cumsum()
    obv_sma = obv.rolling(14).mean()
    s["OBV"] = f"{obv.iloc[-1]:,.0f} (Ort: {obv_sma.iloc[-1]:,.0f})"

    # 6. CCI
    tp = (h + l + c) / 3; sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
    s["CCI (20)"] = round(cci.iloc[-1], 2)

    # 7. ATR
    tr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    atr = rma(tr, 14)
    s["ATR (14) Volatilite"] = round(atr.iloc[-1], 2)

    # 8. ADX / DMI
    up_move = h.diff(); down_move = -l.diff()
    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_s = atr.replace(0, np.nan)
    plus_di  = 100 * rma(pd.Series(plus_dm,  index=c.index), 14) / atr_s
    minus_di = 100 * rma(pd.Series(minus_dm, index=c.index), 14) / atr_s
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    adx = rma(100 * (plus_di - minus_di).abs() / di_sum, 14)
    s["ADX (14) Trend Gücü"] = f"{adx.iloc[-1]:.2f} (+DI: {plus_di.iloc[-1]:.2f} | -DI: {minus_di.iloc[-1]:.2f})"

    # 9. CMF
    hl_diff = (h - l).replace(0, np.nan)
    mfv = ((2*c - l - h) / hl_diff) * v
    cmf = mfv.rolling(20).sum() / v.rolling(20).sum()
    s["CMF (20) Para Akışı"] = round(cmf.iloc[-1], 2)

    # 10. Bollinger
    bb_basis = c.rolling(20).mean(); bb_std = c.rolling(20).std(ddof=0)
    bb_upper = bb_basis + 2*bb_std; bb_lower = bb_basis - 2*bb_std
    s["Bollinger Bantları"] = f"Alt: {bb_lower.iloc[-1]:.2f} | Orta: {bb_basis.iloc[-1]:.2f} | Üst: {bb_upper.iloc[-1]:.2f}"
    s["BB Genişliği (%)"] = round(((bb_upper - bb_lower) / bb_basis * 100).iloc[-1], 2)
    s["BB %B"]            = round(((c - bb_lower) / (bb_upper - bb_lower).replace(0,np.nan)).iloc[-1], 2)

    # 11. Ichimoku
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun  = (h.rolling(26).max() + l.rolling(26).min()) / 2
    sa = ((tenkan+kijun)/2).shift(26); sb = ((h.rolling(52).max()+l.rolling(52).min())/2).shift(26)
    s["Ichimoku (Tenkan/Kijun)"] = f"{tenkan.iloc[-1]:.2f} / {kijun.iloc[-1]:.2f}"
    s["Ichimoku Bulut"] = "Yeşil (Yükselen)" if sa.iloc[-1] > sb.iloc[-1] else "Kırmızı (Düşen)"

    # 12. Momentum
    s["Momentum (10)"] = round((c - c.shift(10)).iloc[-1], 2)

    # 13. RVOL
    avg_vol_10 = v.shift(1).rolling(10).mean()
    s["Göreceli Hacim (RVOL)"] = round((v / avg_vol_10.replace(0, np.nan)).iloc[-1], 2)

    # 14. Pivot
    ph_, pl_, pc_ = h.iloc[-2], l.iloc[-2], c.iloc[-2]
    pv = (ph_ + pl_ + pc_) / 3
    s["Pivot (Geleneksel)"] = (
        f"P: {pv:.2f} | "
        f"R1: {2*pv-pl_:.2f} | S1: {2*pv-ph_:.2f} | "
        f"R2: {pv+(ph_-pl_):.2f} | S2: {pv-(ph_-pl_):.2f} | "
        f"R3: {ph_+2*(pv-pl_):.2f} | S3: {pl_-2*(ph_-pv):.2f}"
    )

    # 15. Hareketli Ortalamalar
    ma_periodlari = [5, 8, 13, 20, 21, 34, 50, 55, 89, 100, 144, 233, 377, 610]
    sma_list, ema_list, wma_list = [], [], []
    for p in ma_periodlari:
        if len(c) >= p:
            sma_list.append(f"{p}g:{c.rolling(p).mean().iloc[-1]:.1f}")
            ema_list.append(f"{p}g:{c.ewm(span=p,adjust=False).mean().iloc[-1]:.1f}")
            wma_list.append(f"{p}g:{wma(c,p).iloc[-1]:.1f}")
        else:
            sma_list.append(f"{p}g:-"); ema_list.append(f"{p}g:-"); wma_list.append(f"{p}g:-")

    s["SMA (Basit)"]     = " | ".join(sma_list)
    s["EMA (Üstel)"]     = " | ".join(ema_list)
    s["WMA (Ağırlıklı)"] = " | ".join(wma_list)

    return s
