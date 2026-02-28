import yfinance as yf
import pandas as pd
import numpy as np
from cache_yonetici import taze_ticker


# ─────────────────────────────────────────────
#  PINE SCRIPT MATEMATİKSEL FONKSİYONLARI
# ─────────────────────────────────────────────

def rma(series: pd.Series, length: int) -> pd.Series:
    """Pine Script ta.rma — Wilder's Moving Average."""
    return series.ewm(alpha=1 / length, adjust=False).mean()


def wma(series: pd.Series, length: int) -> pd.Series:
    """Pine Script ta.wma — Ağırlıklı Hareketli Ortalama."""
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


# ─────────────────────────────────────────────
#  RSI DIVERGENCE
# ─────────────────────────────────────────────

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


def _rsi_divergence(rsi, price, lookback_left=5, lookback_right=5,
                    range_lower=5, range_upper=60):
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


# ─────────────────────────────────────────────
#  SUPERTREND  (Pine Script ta.supertrend birebir)
#  factor=3.0, atrPeriod=10
# ─────────────────────────────────────────────

def _supertrend(h: pd.Series, l: pd.Series, c: pd.Series,
                factor: float = 3.0, atr_period: int = 10):
    """
    Pine Script ta.supertrend(factor, atrPeriod) karşılığı.
    direction: -1 = yükselen trend (fiyat üzerinde destek),
               +1 = düşen trend (fiyat üzerinde direnç)
    Döner: (supertrend Series, direction Series)
    """
    # ATR — Pine ta.supertrend içinde ta.rma kullanır
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = rma(tr, atr_period)

    hl2    = (h + l) / 2
    upper  = hl2 + factor * atr   # basic upper band
    lower  = hl2 - factor * atr   # basic lower band

    # Final bantlar — Pine'daki bant kıstırma (band clamping) mantığı
    final_upper = pd.Series(np.nan, index=c.index)
    final_lower = pd.Series(np.nan, index=c.index)
    direction   = pd.Series(np.nan, index=c.index)
    supertrend  = pd.Series(np.nan, index=c.index)

    for i in range(1, len(c)):
        # Upper band: bir önceki upper'dan yüksekse veya önceki kapanış altındaysa sıfırla
        if upper.iloc[i] < final_upper.iloc[i-1] or c.iloc[i-1] > final_upper.iloc[i-1]:
            final_upper.iloc[i] = upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i-1]

        # Lower band: bir önceki lower'dan düşükse veya önceki kapanış üzerindeyse sıfırla
        if lower.iloc[i] > final_lower.iloc[i-1] or c.iloc[i-1] < final_lower.iloc[i-1]:
            final_lower.iloc[i] = lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i-1]

        # Yön belirleme
        prev_dir = direction.iloc[i-1] if not np.isnan(direction.iloc[i-1]) else 1
        prev_st  = supertrend.iloc[i-1] if not np.isnan(supertrend.iloc[i-1]) else final_upper.iloc[i]

        if prev_st == final_upper.iloc[i-1]:
            # Önceki bar direnç bandındaydı
            if c.iloc[i] > final_upper.iloc[i]:
                direction.iloc[i] = -1  # kırıldı → yükselen trend
            else:
                direction.iloc[i] =  1
        else:
            # Önceki bar destek bandındaydı
            if c.iloc[i] < final_lower.iloc[i]:
                direction.iloc[i] =  1  # kırıldı → düşen trend
            else:
                direction.iloc[i] = -1

        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == -1 else final_upper.iloc[i]

    return supertrend, direction


# ─────────────────────────────────────────────
#  ALPHATREND  (KivancOzbilgic — Pine Script v5)
#  coeff=1.0, AP=14, MFI tabanlı (hacim verisi var)
# ─────────────────────────────────────────────

def _mfi(h, l, c, v, length):
    """Money Flow Index — Pine Script ta.mfi(hlc3, AP) karşılığı."""
    hlc3   = (h + l + c) / 3
    mf     = hlc3 * v
    delta  = hlc3.diff()
    pos_mf = mf.where(delta > 0, 0.0)
    neg_mf = mf.where(delta < 0, 0.0)
    pos_sum = pos_mf.rolling(length).sum()
    neg_sum = neg_mf.rolling(length).sum().abs()
    mfr    = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - (100 / (1 + mfr))


def _alphatrend(h, l, c, v, coeff=1.0, ap=14):
    """
    AlphaTrend by KivancOzbilgic.
    MFI >= 50  → upT = low  - ATR*coeff  (destek bant)
    MFI <  50  → downT = high + ATR*coeff (direnç bant)
    Sinyal: AlphaTrend çizgisinin 2 bar gecikmeli versiyonuyla kesişim.
    """
    # ATR: Pine kodunda ta.sma(ta.tr, AP) — dikkat: rma değil sma
    tr  = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(ap).mean()   # ta.sma

    mfi = _mfi(h, l, c, v, ap)

    upT   = l - atr * coeff
    downT = h + atr * coeff

    at = pd.Series(0.0, index=c.index)

    for i in range(1, len(c)):
        prev = at.iloc[i - 1]
        if mfi.iloc[i] >= 50:
            # Yükselen koşul: upT < önceki AT ise önceki AT'yi koru
            at.iloc[i] = upT.iloc[i] if upT.iloc[i] > prev else prev
        else:
            # Düşen koşul: downT > önceki AT ise önceki AT'yi koru
            at.iloc[i] = downT.iloc[i] if downT.iloc[i] < prev else prev

    return at


# ─────────────────────────────────────────────
#  ANA FONKSİYON
# ─────────────────────────────────────────────

def teknik_analiz_yap(ticker_symbol: str) -> dict:
    hisse = taze_ticker(ticker_symbol)
    df    = hisse.history(period="3y")   # 610 bar için 3 yıl yeterli
    if df.empty or len(df) < 60:
        return {"Hata": "Yeterli fiyat geçmişi yok."}

    c = df["Close"]; h = df["High"]; l = df["Low"]; v = df["Volume"]
    o = df["Open"]
    delta = c.diff()
    s = {}
    s["Güncel Fiyat"] = round(c.iloc[-1], 2)

    # ── 1. RSI ───────────────────────────────────────────────────────────────
    up = delta.clip(lower=0); down = (-delta).clip(lower=0)
    rma_up = rma(up, 14); rma_down = rma(down, 14)
    rsi_arr = np.where(rma_down == 0, 100,
              np.where(rma_up   == 0,   0,
                       100 - (100 / (1 + rma_up / rma_down))))
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

    # ── 2. Stoch RSI ─────────────────────────────────────────────────────────
    rsi_ll = rsi.rolling(14).min(); rsi_hh = rsi.rolling(14).max()
    stoch  = 100 * (rsi - rsi_ll) / (rsi_hh - rsi_ll).replace(0, np.nan)
    k_line = stoch.rolling(3).mean(); d_line = k_line.rolling(3).mean()
    s["Stoch RSI (K / D)"] = f"{k_line.iloc[-1]:.2f} / {d_line.iloc[-1]:.2f}"

    # ── 3. SMI ───────────────────────────────────────────────────────────────
    hh_10 = h.rolling(10).max(); ll_10 = l.rolling(10).min()
    hl_range = hh_10 - ll_10; rel_range = c - (hh_10 + ll_10) / 2
    ema2_rel = rel_range.ewm(span=3, adjust=False).mean().ewm(span=3, adjust=False).mean()
    ema2_hl  = hl_range.ewm(span=3, adjust=False).mean().ewm(span=3, adjust=False).mean()
    smi = 200 * (ema2_rel / ema2_hl.replace(0, np.nan))
    s["SMI (Stokastik Momentum)"] = round(smi.iloc[-1], 2)

    # ── 4. MACD ──────────────────────────────────────────────────────────────
    macd   = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    s["MACD (12,26,9)"] = (f"Hat: {macd.iloc[-1]:.2f} | "
                           f"Sinyal: {signal.iloc[-1]:.2f} | "
                           f"Histogram: {(macd-signal).iloc[-1]:.2f}")

    # ── 5. CCI ───────────────────────────────────────────────────────────────
    tp     = (h + l + c) / 3; sma_tp = tp.rolling(20).mean()
    mad    = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    cci    = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
    s["CCI (20)"] = round(cci.iloc[-1], 2)

    # ── 6. ATR ───────────────────────────────────────────────────────────────
    tr  = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = rma(tr, 14)
    s["ATR (14) Volatilite"] = round(atr.iloc[-1], 2)

    # ── 7. ADX / DMI ─────────────────────────────────────────────────────────
    up_move = h.diff(); down_move = -l.diff()
    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_s    = atr.replace(0, np.nan)
    plus_di  = 100 * rma(pd.Series(plus_dm,  index=c.index), 14) / atr_s
    minus_di = 100 * rma(pd.Series(minus_dm, index=c.index), 14) / atr_s
    di_sum   = (plus_di + minus_di).replace(0, np.nan)
    adx      = rma(100 * (plus_di - minus_di).abs() / di_sum, 14)
    s["ADX (14) Trend Gücü"] = (f"{adx.iloc[-1]:.2f} "
                                f"(+DI: {plus_di.iloc[-1]:.2f} | -DI: {minus_di.iloc[-1]:.2f})")

    # ── 8. CMF ───────────────────────────────────────────────────────────────
    hl_diff = (h - l).replace(0, np.nan)
    mfv     = ((2 * c - l - h) / hl_diff) * v
    cmf     = mfv.rolling(20).sum() / v.rolling(20).sum()
    s["CMF (20) Para Akışı"] = round(cmf.iloc[-1], 2)

    # ── 9. Bollinger Bantları ─────────────────────────────────────────────────
    bb_basis = c.rolling(20).mean(); bb_std = c.rolling(20).std(ddof=0)
    bb_upper = bb_basis + 2 * bb_std; bb_lower = bb_basis - 2 * bb_std
    s["Bollinger Bantları"] = (f"Alt: {bb_lower.iloc[-1]:.2f} | "
                               f"Orta: {bb_basis.iloc[-1]:.2f} | "
                               f"Üst: {bb_upper.iloc[-1]:.2f}")
    s["BB Genişliği (%)"] = round(((bb_upper - bb_lower) / bb_basis * 100).iloc[-1], 2)
    s["BB %B"]            = round(((c - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)).iloc[-1], 2)

    # ── 10. Ichimoku ─────────────────────────────────────────────────────────
    tenkan = (h.rolling(9).max()  + l.rolling(9).min())  / 2
    kijun  = (h.rolling(26).max() + l.rolling(26).min()) / 2
    sa     = ((tenkan + kijun) / 2).shift(26)
    sb     = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    s["Ichimoku (Tenkan/Kijun)"] = f"{tenkan.iloc[-1]:.2f} / {kijun.iloc[-1]:.2f}"
    s["Ichimoku Bulut"] = "Yeşil (Yükselen)" if sa.iloc[-1] > sb.iloc[-1] else "Kırmızı (Düşen)"

    # ── 11. Momentum ─────────────────────────────────────────────────────────
    s["Momentum (10)"] = round((c - c.shift(10)).iloc[-1], 2)

    # ── 12. Göreceli Hacim (RVOL) ─────────────────────────────────────────────
    avg_vol_10 = v.shift(1).rolling(10).mean()
    s["Göreceli Hacim (RVOL)"] = round((v / avg_vol_10.replace(0, np.nan)).iloc[-1], 2)

    # ── 13. Supertrend (factor=3.0, period=10) ───────────────────────────────
    try:
        st_val, st_dir = _supertrend(h, l, c, factor=3.0, atr_period=10)
        dir_son   = int(st_dir.iloc[-1])
        dir_once  = int(st_dir.iloc[-2]) if len(st_dir) > 1 else dir_son
        yön       = "📈 Yükselen" if dir_son == -1 else "📉 Düşen"
        # Trend değişimi kontrolü
        degisim   = ""
        if dir_son != dir_once:
            degisim = " ⚡ YENİ SİNYAL"
        s["Supertrend (3,10)"] = f"{st_val.iloc[-1]:.2f} — {yön}{degisim}"
    except Exception as e:
        s["Supertrend (3,10)"] = "Hesaplanamadı"

    # ── 14. AlphaTrend (coeff=1.0, period=14, MFI tabanlı) ───────────────────
    try:
        at   = _alphatrend(h, l, c, v, coeff=1.0, ap=14)
        at2  = at.shift(2)   # AlphaTrend[2] — sinyal için 2 bar gecikme
        # Yön: AT > AT[2] → yükselen, AT < AT[2] → düşen
        if at.iloc[-1] > at2.iloc[-1]:
            at_yon = "📈 Yükselen"
        else:
            at_yon = "📉 Düşen"
        # Al/Sat sinyali: son kesişim
        crossover  = (at.iloc[-1] > at2.iloc[-1]) and (at.iloc[-2] <= at2.iloc[-2])
        crossunder = (at.iloc[-1] < at2.iloc[-1]) and (at.iloc[-2] >= at2.iloc[-2])
        sinyal = ""
        if crossover:
            sinyal = " ✅ AL Sinyali"
        elif crossunder:
            sinyal = " 🔴 SAT Sinyali"
        s["AlphaTrend (1,14)"] = f"{at.iloc[-1]:.2f} — {at_yon}{sinyal}"
    except Exception:
        s["AlphaTrend (1,14)"] = "Hesaplanamadı"

    # ── 15. Pivot Noktaları ───────────────────────────────────────────────────
    ph_, pl_, pc_ = h.iloc[-2], l.iloc[-2], c.iloc[-2]
    pv = (ph_ + pl_ + pc_) / 3
    s["Pivot (Geleneksel)"] = (
        f"P: {pv:.2f} | "
        f"R1: {2*pv-pl_:.2f} | S1: {2*pv-ph_:.2f} | "
        f"R2: {pv+(ph_-pl_):.2f} | S2: {pv-(ph_-pl_):.2f} | "
        f"R3: {ph_+2*(pv-pl_):.2f} | S3: {pl_-2*(ph_-pv):.2f}"
    )

    # ── 16. Hareketli Ortalamalar ─────────────────────────────────────────────
    ma_periodlari = [5, 8, 13, 20, 21, 34, 50, 55, 89, 100, 144, 233, 377, 610]
    sma_list, ema_list, wma_list = [], [], []
    for p in ma_periodlari:
        if len(c) >= p:
            sma_list.append(f"{p}g:{c.rolling(p).mean().iloc[-1]:.1f}")
            ema_list.append(f"{p}g:{c.ewm(span=p, adjust=False).mean().iloc[-1]:.1f}")
            wma_list.append(f"{p}g:{wma(c, p).iloc[-1]:.1f}")
        else:
            sma_list.append(f"{p}g:-"); ema_list.append(f"{p}g:-"); wma_list.append(f"{p}g:-")

    s["SMA (Basit)"]     = " | ".join(sma_list)
    s["EMA (Üstel)"]     = " | ".join(ema_list)
    s["WMA (Ağırlıklı)"] = " | ".join(wma_list)

    return s
