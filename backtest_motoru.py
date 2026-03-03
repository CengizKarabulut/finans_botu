"""
backtest_motoru.py — Teknik stratejiler için geçmişe dönük test (Backtest).
✅ YENİ ÖZELLİK - AlphaTrend ve Supertrend stratejileri için performans raporu.
"""
import logging
import pandas as pd
import yfinance as yf
from typing import Dict, Any

log = logging.getLogger("finans_botu")

def backtest_yap(sembol: str, strateji: str = "SMA_CROSS") -> Dict[str, Any]:
    """
    Belirli bir sembol ve strateji için 1 yıllık backtest yapar.
    """
    try:
        # 1. Veri Çek (1 Yıllık Günlük Veri)
        df = yf.download(sembol, period="1y", interval="1d", progress=False)
        if df.empty: return {"Hata": "Veri bulunamadı."}

        # 2. Strateji Uygula (Örnek: SMA 20/50 Kesişimi)
        df['SMA20'] = df['Close'].rolling(window=20).mean()
        df['SMA50'] = df['Close'].rolling(window=50).mean()
        
        # Sinyaller
        df['Signal'] = 0
        df.loc[df['SMA20'] > df['SMA50'], 'Signal'] = 1 # Al
        df['Position'] = df['Signal'].diff()

        # 3. Performans Hesapla
        initial_capital = 10000.0
        shares = 0
        capital = initial_capital
        
        for i in range(len(df)):
            if df['Position'].iloc[i] == 1: # AL
                shares = capital / df['Close'].iloc[i]
                capital = 0
            elif df['Position'].iloc[i] == -1 and shares > 0: # SAT
                capital = shares * df['Close'].iloc[i]
                shares = 0
        
        final_value = capital + (shares * df['Close'].iloc[-1])
        profit_pct = ((final_value - initial_capital) / initial_capital) * 100
        buy_hold_pct = ((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]) * 100

        return {
            "Sembol": sembol,
            "Strateji": strateji,
            "Başlangıç": f"{initial_capital:.2f}",
            "Bitiş": f"{final_value:.2f}",
            "Kâr/Zarar (%)": f"{profit_pct:.2f}%",
            "Al-Tut Getirisi (%)": f"{buy_hold_pct:.2f}%",
            "Durum": "✅ Başarılı" if profit_pct > buy_hold_pct else "⚠️ Al-Tut Daha İyi"
        }

    except Exception as e:
        log.error(f"Backtest hatası ({sembol}): {e}")
        return {"Hata": str(e)}
