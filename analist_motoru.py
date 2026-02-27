import os
import google.generativeai as genai
from groq import Groq

# ─────────────────────────────────────────────
#  TAM KAPSAMLI BAĞLAM OLUŞTURUCU (Senin Orijinal Mantığın)
# ─────────────────────────────────────────────

def _veri_ozeti_olustur(hisse_kodu: str, temel: dict, teknik: dict) -> str:
    def _al(d: dict, *anahtarlar, varsayilan="N/A"):
        for k in anahtarlar:
            v = d.get(k)
            if v is not None and v != 0 and v != "" and v != "N/A":
                return v
        return varsayilan

    def _rsi_deger(rsi_str: str) -> float:
        try:
            return float(str(rsi_str).split()[0])
        except Exception:
            return 50.0

    sektor  = _al(temel, "Firma Sektörü")
    para_br = _al(temel, "Para Birimi")
    fiyat   = _al(temel, "Fiyat")

    # EMA trend özeti işleme (Senin kodundaki detaylı mantık)
    ema_ozet = ""
    try:
        ema_str = teknik.get("EMA (Üstel)", "")
        if ema_str:
            ema_dict = {p.split(":")[0].strip(): float(p.split(":")[1].strip()) for p in ema_str.split("|") if ":" in p}
            if fiyat and fiyat != "N/A":
                fiyat_f = float(fiyat)
                altta = sum(1 for v in ema_dict.values() if fiyat_f > v)
                ema_ozet = f"Fiyat {altta}/{len(ema_dict)} EMA'nın üzerinde."
    except: pass

    # AI'ya gidecek devasa veri paketi
    return f"""
HİSSE: {hisse_kodu} | Sektör: {sektor} | Para Birimi: {para_br} | Fiyat: {fiyat}

=== DEĞERLEME (VALUATION) ===
F/K: {_al(temel, "F/K (Günlük)", "F/K (Hesaplanan)")} | PD/DD: {_al(temel, "PD/DD (Günlük)", "PD/DD (Hesaplanan)")}
FD/FAVÖK: {_al(temel, "FD/FAVÖK (Günlük)", "EV/EBITDA (Hesaplanan)")}
PEG: {_al(temel, "PEG Oranı (Hesaplanan)", "PEG Oranı (Günlük)")} | F/S: {_al(temel, "F/S (Fiyat/Satış)")}

=== KARLILIK (PROFITABILITY) ===
Net Kar Marjı (Y/Ç): {_al(temel, "Net Kar Marjı — Yıllık (%)")}% / {_al(temel, "Net Kar Marjı — Çeyreklik (%)")}%
Brüt Kar Marjı (Y): {_al(temel, "Brüt Kar Marjı — Yıllık (%)")}%
FAVÖK Marjı (Y/Ç): {_al(temel, "FAVÖK Marjı — Yıllık (%)")}% / {_al(temel, "FAVÖK Marjı — Çeyreklik (%)")}%
ROE: {_al(temel, "Özsermaye Karlılığı (ROE) — Yıllık")}% | ROA: {_al(temel, "Varlık Karlılığı (ROA) — Yıllık")}%
ROIC: {_al(temel, "ROIC (%)")}%

=== BÜYÜME (GROWTH) ===
Satış Büyümesi (Yıllık): {_al(temel, "Satış Büyümesi — Yıllık (%)")}% | Kar Büyümesi: {_al(temel, "Net Kar Büyümesi — Yıllık (%)")}%
Satış YoY (Çeyrek): {_al(temel, "Satış Büyümesi — YoY (%)")}% | Satış QoQ: {_al(temel, "Satış Büyümesi — QoQ (%)")}%

=== BORÇ & LİKİDİTE ===
Cari Oran: {_al(temel, "Cari Oran")} | D/E: {_al(temel, "Borç / Özsermaye (D/E)")}
Net Borç/FAVÖK: {_al(temel, "Net Borç / FAVÖK")} | Faiz Karşılama: {_al(temel, "Faiz Karşılama Oranı")}

=== NAKİT AKIŞI & TEMETTÜ ===
FCF Getirisi: {_al(temel, "FCF Getirisi (%)")}% | FCF/Net Kar: {_al(temel, "FCF / Net Kar")}
Temettü Verimi: {_al(temel, "Temettü Verimi (%)")}%

=== TEKNİK GÖSTERGELER ===
RSI: {_al(teknik, "RSI (14)")} | RSI Div: {_al(teknik, "RSI Divergence")}
Stoch RSI: {_al(teknik, "Stoch RSI (K / D)")} | MACD: {_al(teknik, "MACD (12,26,9)")}
ADX (Trend): {_al(teknik, "ADX (14) Trend Gücü")} | Para Akışı (CMF): {_al(teknik, "CMF (20) Para Akışı")}
Bollinger: {_al(teknik, "Bollinger Bantları")} | BB %B: {_al(teknik, "BB %B")}
Supertrend: {_al(teknik, "Supertrend (3,10)")} | AlphaTrend: {_al(teknik, "AlphaTrend (1,14)")}
Momentum: {_al(teknik, "Momentum (10)")} | RVOL: {_al(teknik, "Göreceli Hacim (RVOL)")}
Pivot: {_al(teknik, "Pivot (Geleneksel)")}
EMA Durumu: {ema_ozet}
""".strip()

# ─────────────────────────────────────────────
#  SİSTEM PROMPTU (Uzman Analist Rolü)
# ─────────────────────────────────────────────

SISTEM_PROMPTU = """Sen kıdemli bir borsa analistisin. Sana sağlanan yukarıdaki temel ve teknik verileri kullanarak 
detaylı, rakamlara dayalı ve profesyonel bir Türkçe rapor hazırla. 

RAPOR YAPISI:
1. **ÖZET GÖRÜŞ**: Hisse genel olarak ne durumda? (Güçlü/Zayıf/Nötr)
2. **TEMEL ANALİZ**: Değerleme çarpanları, karlılık marjları ve büyüme verilerini yorumla.
3. **TEKNİK ANALİZ**: Trend yönü (EMA/Supertrend), momentum (RSI/MACD) ve hacim (RVOL) göstergelerini değerlendir.
4. **GÜÇLÜ & ZAYIF YÖNLER**: Verilere dayanarak en fazla 3'er madde yaz.
5. **RİSK DEĞERLENDİRMESİ**: Borçluluk ve teknik riskleri belirt.
6. **NOT**: Sonunda 'Yatırım tavsiyesi değildir' uyarısı yap.

KURALLAR:
- Veriler N/A ise o konuya girme. 
- Rakamları metin içinde mutlaka kullan (Örn: "Net borç/FAVÖK oranı 4.5 ile riskli seviyede")."""

# ─────────────────────────────────────────────
#  ANA HİBRİT MOTOR
# ─────────────────────────────────────────────

def ai_analist_yorumu(hisse_kodu: str, temel_veriler: dict, teknik_veriler: dict) -> str:
    baglam = _veri_ozeti_olustur(hisse_kodu, temel_veriler, teknik_veriler)
    prompt = f"{hisse_kodu} için veriler aşağıdadır:\n\n{baglam}"

    # 1. ÖNCELİK: GEMINI FLASH (Senin hesabın/API üzerinden)
    api_key_gemini = os.environ.get("GEMINI_API_KEY")
    if api_key_gemini:
        try:
            genai.configure(api_key=api_key_gemini)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content([SISTEM_PROMPTU, prompt])
            return "✨ [Gemini Analiz Raporu]\n\n" + response.text
        except Exception as e:
            print(f"Gemini hatası: {e}. Groq'a geçiliyor...")

    # 2. YEDEK: GROQ (Llama 3.3 70B)
    api_key_groq = os.environ.get("GROQ_API_KEY")
    if api_key_groq:
        try:
            client = Groq(api_key=api_key_groq)
            yanit = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": SISTEM_PROMPTU}, {"role": "user", "content": prompt}]
            )
            return "🦙 [Llama 3.3 Analiz Raporu]\n\n" + yanit.choices[0].message.content
        except Exception as e:
            return f"Hata: İki AI motoru da başarısız oldu. Son hata: {str(e)}"

    return "API Key tanımlı değil. GEMINI_API_KEY veya GROQ_API_KEY ortam değişkenlerini kontrol edin."
