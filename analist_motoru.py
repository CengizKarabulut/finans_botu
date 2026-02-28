"""
analist_motoru.py — AI Analist Motoru (Groq / Llama 3.3 70B)

Groq ucretsiz tier: 14.400 istek/gun, 70K token/dakika.

Kurulum:
  pip install groq

API Key:
  console.groq.com -> ucretsiz kayit -> API Keys -> yeni key olustur
  export GROQ_API_KEY="gsk_..."
"""

import os
from groq import Groq


# ─────────────────────────────────────────────
#  BAGAM OLUSTURUCU
# ─────────────────────────────────────────────

def _veri_ozeti_olustur(hisse_kodu: str, temel: dict, teknik: dict) -> str:

    def _al(d, *anahtarlar, varsayilan="N/A"):
        for k in anahtarlar:
            v = d.get(k)
            if v is not None and v != 0 and v != "" and v != "N/A":
                return v
        return varsayilan

    def _rsi_deger(rsi_str):
        try:
            return float(str(rsi_str).split()[0])
        except Exception:
            return 50.0

    # Temel
    sektor     = _al(temel, "Firma Sektoru")
    para_br    = _al(temel, "Para Birimi")
    fiyat      = _al(temel, "Fiyat")
    fk         = _al(temel, "F/K (Gunluk)", "F/K (Hesaplanan)")
    pddd       = _al(temel, "PD/DD (Gunluk)", "PD/DD (Hesaplanan)")
    fd_favk    = _al(temel, "FD/FAVOK (Gunluk)", "EV/EBITDA (Hesaplanan)")
    peg        = _al(temel, "PEG Orani (Hesaplanan)", "PEG Orani (Gunluk)")
    fs         = _al(temel, "F/S (Fiyat/Satis)")
    net_mar_y  = _al(temel, "Net Kar Marji \u2014 Yillik (%)")
    brut_mar_y = _al(temel, "Brut Kar Marji \u2014 Yillik (%)")
    favk_mar_y = _al(temel, "FAVOK Marji \u2014 Yillik (%)")
    net_mar_q  = _al(temel, "Net Kar Marji \u2014 Ceyreklik (%)")
    favk_mar_q = _al(temel, "FAVOK Marji \u2014 Ceyreklik (%)")
    roe        = _al(temel, "Ozsermaye Karliligi (ROE) \u2014 Yillik")
    roa        = _al(temel, "Varlik Karliligi (ROA) \u2014 Yillik")
    roic       = _al(temel, "ROIC (%)")
    satis_y    = _al(temel, "Satis Buyumesi \u2014 Yillik (%)")
    kar_y      = _al(temel, "Net Kar Buyumesi \u2014 Yillik (%)")
    satis_yoy  = _al(temel, "Satis Buyumesi \u2014 YoY (%)")
    satis_qoq  = _al(temel, "Satis Buyumesi \u2014 QoQ (%)")
    cari       = _al(temel, "Cari Oran")
    de         = _al(temel, "Borc / Ozsermaye (D/E)")
    net_borc_f = _al(temel, "Net Borc / FAVOK")
    faiz_kar   = _al(temel, "Faiz Karsilama Orani")
    fcf_get    = _al(temel, "FCF Getirisi (%)")
    fcf_kar    = _al(temel, "FCF / Net Kar")
    temettu    = _al(temel, "Temettu Verimi (%)")

    # Teknik
    rsi_raw    = _al(teknik, "RSI (14)", varsayilan="50")
    rsi        = _rsi_deger(rsi_raw)
    rsi_div    = _al(teknik, "RSI Divergence", varsayilan="Yok")
    stoch      = _al(teknik, "Stoch RSI (K / D)")
    macd       = _al(teknik, "MACD (12,26,9)")
    adx        = _al(teknik, "ADX (14) Trend Gucu")
    cmf        = _al(teknik, "CMF (20) Para Akisi")
    bb         = _al(teknik, "Bollinger Bantlari")
    bb_pb      = _al(teknik, "BB %B")
    ichi_bulut = _al(teknik, "Ichimoku Bulut")
    ichi_tk    = _al(teknik, "Ichimoku (Tenkan/Kijun)")
    supertrend = _al(teknik, "Supertrend (3,10)")
    alphatrend = _al(teknik, "AlphaTrend (1,14)")
    momentum   = _al(teknik, "Momentum (10)")
    rvol       = _al(teknik, "Goreceli Hacim (RVOL)")
    pivot      = _al(teknik, "Pivot (Geleneksel)")

    # EMA pozisyon ozeti
    ema_ozet = "N/A"
    try:
        ema_str  = teknik.get("EMA (\u00dcstsel)", "")
        ema_dict = {}
        for p in ema_str.split("|"):
            p = p.strip()
            if ":" in p and "g" in p:
                k, v = p.split(":", 1)
                gun = int(k.strip().replace("g", ""))
                ema_dict[gun] = float(v.strip())
        if ema_dict and fiyat != "N/A":
            fiyat_f = float(fiyat)
            uzerin  = sum(1 for v in ema_dict.values() if fiyat_f > v)
            ema_ozet = (
                f"Fiyat {uzerin}/{len(ema_dict)} EMA'nin uzerinde. "
                f"EMA20={ema_dict.get(20,'?')}, "
                f"EMA50={ema_dict.get(50,'?')}, "
                f"EMA200={ema_dict.get(200,'?')}"
            )
    except Exception:
        pass

    return (
        f"HISSE: {hisse_kodu} | Sektor: {sektor} | Para Birimi: {para_br} | Fiyat: {fiyat}\n\n"
        f"=== DEGERLEME ===\n"
        f"F/K: {fk} | PD/DD: {pddd} | FD/FAVOK: {fd_favk} | PEG: {peg} | F/S: {fs}\n\n"
        f"=== KARLILIK ===\n"
        f"Net Kar Marji Y/Q: {net_mar_y}% / {net_mar_q}% | Brut Marj: {brut_mar_y}%\n"
        f"FAVOK Marji Y/Q: {favk_mar_y}% / {favk_mar_q}%\n"
        f"ROE: {roe}% | ROA: {roa}% | ROIC: {roic}%\n\n"
        f"=== BUYUME ===\n"
        f"Satis (Yillik): {satis_y}% | Net Kar (Yillik): {kar_y}%\n"
        f"Satis YoY: {satis_yoy}% | QoQ: {satis_qoq}%\n\n"
        f"=== BORC & LIKIDITE ===\n"
        f"Cari Oran: {cari} | D/E: {de} | Net Borc/FAVOK: {net_borc_f} | Faiz Karsilama: {faiz_kar}\n\n"
        f"=== NAKIT AKISI ===\n"
        f"FCF Getirisi: {fcf_get}% | FCF/Net Kar: {fcf_kar} | Temettu: {temettu}%\n\n"
        f"=== TEKNIK ===\n"
        f"RSI: {rsi} | Divergence: {rsi_div}\n"
        f"Stoch RSI: {stoch} | MACD: {macd}\n"
        f"ADX: {adx} | CMF: {cmf}\n"
        f"Bollinger: {bb} | BB %B: {bb_pb}\n"
        f"Ichimoku: {ichi_bulut} | Tenkan/Kijun: {ichi_tk}\n"
        f"Supertrend: {supertrend} | AlphaTrend: {alphatrend}\n"
        f"Momentum: {momentum} | RVOL: {rvol}\n"
        f"Pivot: {pivot}\n"
        f"EMA Durumu: {ema_ozet}"
    )


# ─────────────────────────────────────────────
#  SISTEM PROMPTU
# ─────────────────────────────────────────────

SISTEM_PROMPTU = """Sen kıdemli bir Türk borsası (BIST) ve uluslararası piyasa analistisin. 15+ yıl deneyimle hem temel hem teknik analizi derinlemesine yorumlayabiliyorsun.

Sana bir hissenin ham verileri verilecek. Bu verileri sentezleyerek kurumsal kalitede, Türkçe, rakamlara dayalı bir analist raporu yaz.

═══ RAPOR YAPISI ═══

1. ÖZET GÖRÜŞ
Tek paragraf. Hissenin genel durumunu net bir etiketle değerlendir:
"Güçlü Alım Bölgesi / Alım Bölgesi / Nötr / Satım Bölgesi / Güçlü Satım Bölgesi"
Neden bu etiketi seçtiğini 2-3 cümleyle açıkla.

2. TEMEL ANALİZ
Değerleme: F/K, PD/DD, FD/FAVÖK rakamlarını sektör normlarıyla kıyasla. Pahalı mı ucuz mu?
Büyüme: Yıllık ve çeyreklik büyüme hızını yorumla. Sürdürülebilir mi? İvme kazanıyor mu kaybediyor mu?
Karlılık: Marjların trendi ne söylüyor? ROE/ROA sektör için iyi mi?
Bilanço: Borç yapısı, cari oran, FCF kalitesi. Risk mi fırsat mı?

3. TEKNİK ANALİZ
Trend: Supertrend, AlphaTrend ve EMA durumuna göre ana trend yönü ne?
Momentum: RSI seviyesi (aşırı alım/satım?), MACD sinyali, Stoch RSI konumu.
Hacim & Para Akışı: RVOL yüksekse hacim teyidi var mı? CMF para girişi mi çıkışı mı gösteriyor?
Kritik Seviyeler: Bollinger bantları, Pivot destek/dirençleri. Fiyat nerede?
Uyarılar: RSI divergence, trend değişim sinyali varsa özellikle vurgula.

4. GÜÇLÜ YÖNLER (en fazla 4 madde, her biri 1 cümle, rakam kullan)
5. ZAYIF YÖNLER (en fazla 4 madde, her biri 1 cümle, rakam kullan)

6. RİSK DEĞERLENDİRMESİ
Temel riskler (borç, karlılık, sektör) ve teknik riskler (kırılacak seviyeler) — 2-3 cümle.

7. YATIRIMCI NOTU
"Bu rapor yatırım tavsiyesi değildir. Yatırım kararlarınızı kendi araştırmanıza ve risk toleransınıza göre verin."

═══ YAZIM KURALLARI ═══
- Rakamları mutlaka kullan: "RSI 63.2 ile henüz aşırı alım bölgesi olan 70'in altında"
- Karşılaştır: "F/K 49 ile savunma sektörü ortalaması olan 20'nin 2.5 katı"
- Belirsiz ifadelerden kaçın: "iyi görünüyor" yerine "net kar marjı %20.4 ile güçlü"
- Çelişkili sinyalleri kabul et: temel güçlüyse ama teknik zayıfsa bunu söyle
- N/A olan verileri yoksay, olmayan veri için yorum yapma
- Maksimum 500 kelime"""


# ─────────────────────────────────────────────
#  ANA FONKSİYON
# ─────────────────────────────────────────────

def ai_analist_yorumu(hisse_kodu: str,
                       temel_veriler: dict,
                       teknik_veriler: dict) -> str:
    """
    1. Önce Gemini Flash (GEMINI_API_KEY varsa)
    2. Yoksa veya hata olursa Groq / Llama 3.3 70B (GROQ_API_KEY)

    Key kurulumu:
      export GEMINI_API_KEY="AIza..."   # aistudio.google.com'dan ücretsiz
      export GROQ_API_KEY="gsk_..."     # console.groq.com'dan ücretsiz
    """
    baglam = _veri_ozeti_olustur(hisse_kodu, temel_veriler, teknik_veriler)
    prompt = f"{hisse_kodu} için verileri analiz et ve raporu hazırla:\n\n{baglam}"

    # ── 1. Gemini Flash ───────────────────────────────────────────────────────
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            from google.genai import types
            client_g = genai.Client(api_key=gemini_key)
            response = client_g.models.generate_content(
                model="gemini-2.5-flash-preview-04-17",
                config=types.GenerateContentConfig(
                    system_instruction=SISTEM_PROMPTU,
                    temperature=0.3,
                    max_output_tokens=1500,
                ),
                contents=prompt,
            )
            return "✨ Gemini Analiz:\n\n" + response.text
        except Exception as e:
            print(f"[Gemini hata] {e} → Groq'a geçiliyor")

    # ── 2. Groq / Llama 3.3 70B ──────────────────────────────────────────────
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            yanit = client.chat.completions.create(
                model       = "llama-3.3-70b-versatile",
                max_tokens  = 1500,
                temperature = 0.3,
                messages    = [
                    {"role": "system", "content": SISTEM_PROMPTU},
                    {"role": "user",   "content": prompt}
                ]
            )
            return "🦙 Llama 3.3 Analiz:\n\n" + yanit.choices[0].message.content
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                return "❌ Groq rate limit aşıldı, 1 dakika sonra tekrar deneyin."
            return f"❌ Groq hatası: {err}"

    return (
        "❌ API key tanımlı değil.\n"
        "Gemini: aistudio.google.com → ücretsiz\n"
        "Groq: console.groq.com → ücretsiz\n"
        "Sunucuda: export GEMINI_API_KEY=... veya export GROQ_API_KEY=..."
    )


# ─────────────────────────────────────────────
#  TERMINAL TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from temel_analiz  import temel_analiz_yap
    from teknik_analiz import teknik_analiz_yap

    hisse = "ASELS.IS"
    print(f"\n{'=' * 60}\n  AI ANALIST  {hisse}\n{'=' * 60}")
    print("Veriler cekiliyor...")
    t  = temel_analiz_yap(hisse)
    tk = teknik_analiz_yap(hisse)
    print("Llama 3.3 70B yorumluyor...\n")
    print(ai_analist_yorumu(hisse, t, tk))
    print(f"\n{'=' * 60}\n")
