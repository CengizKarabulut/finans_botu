import os
from groq import Groq

SISTEM_PROMPTU = """Sen kıdemli bir Türk borsası (BIST) ve uluslararası piyasa analistisin. 15+ yıl deneyimle hem temel hem teknik analizi derinlemesine yorumlayabiliyorsun.

Sana bir hissenin ham verileri verilecek. Bu verileri sentezleyerek kurumsal kalitede, Türkçe, rakamlara dayalı bir analist raporu yaz.

RAPOR YAPISI:

1. ÖZET GÖRÜŞ
Hissenin genel durumunu şu etiketlerden biriyle değerlendir:
"Güçlü Alım Bölgesi / Alım Bölgesi / Nötr / Satım Bölgesi / Güçlü Satım Bölgesi"
Neden bu etiketi seçtiğini 2-3 cümleyle açıkla.

2. TEMEL ANALİZ
Değerleme: F/K, PD/DD, FD/FAVÖK rakamlarını sektör normlarıyla kıyasla. Pahalı mı ucuz mu?
Büyüme: Yıllık ve çeyreklik büyüme hızını yorumla. Sürdürülebilir mi?
Karlılık: Marjların trendi ne söylüyor? ROE/ROA sektör için iyi mi?
Bilanço: Borç yapısı, cari oran, FCF kalitesi.

3. TEKNİK ANALİZ
Trend: Supertrend, AlphaTrend ve EMA durumuna göre ana trend yönü.
Momentum: RSI seviyesi, MACD sinyali, Stoch RSI.
Hacim & Para Akışı: RVOL, CMF yorumu.
Kritik Seviyeler: Bollinger, Pivot destek/dirençler.
Uyarılar: RSI divergence veya trend değişim sinyali varsa vurgula.

4. GÜÇLÜ YÖNLER (en fazla 4 madde, rakam kullan)
5. ZAYIF YÖNLER (en fazla 4 madde, rakam kullan)

6. RİSK DEĞERLENDİRMESİ (2-3 cümle)

7. YATIRIMCI NOTU: Bu rapor yatırım tavsiyesi değildir.

KURALLAR:
- Rakamları mutlaka kullan: "RSI 63.2 ile henüz aşırı alım bölgesi olan 70'in altında"
- Karşılaştır: "F/K 49 ile savunma sektörü ortalaması olan 20'nin 2.5 katı"
- N/A olan verileri yoksay
- Maksimum 500 kelime"""


def _veri_ozeti_olustur(hisse_kodu: str, temel: dict, teknik: dict) -> str:
    def _al(d, *anahtarlar, varsayilan="N/A"):
        for k in anahtarlar:
            v = d.get(k)
            if v is not None and v != 0 and v != "" and v != "N/A":
                return v
        return varsayilan

    def _rsi(rsi_str):
        try:
            return float(str(rsi_str).split()[0])
        except:
            return 50.0

    fk         = _al(temel, "F/K (Günlük)", "F/K (Hesaplanan)")
    pddd       = _al(temel, "PD/DD (Günlük)", "PD/DD (Hesaplanan)")
    fd_favk    = _al(temel, "FD/FAVÖK (Günlük)", "EV/EBITDA (Hesaplanan)")
    peg        = _al(temel, "PEG Oranı (Hesaplanan)", "PEG Oranı (Günlük)")
    fs         = _al(temel, "F/S (Fiyat/Satış)")
    net_mar_y  = _al(temel, "Net Kar Marjı — Yıllık (%)")
    brut_mar_y = _al(temel, "Brüt Kar Marjı — Yıllık (%)")
    favk_mar_y = _al(temel, "FAVÖK Marjı — Yıllık (%)")
    net_mar_q  = _al(temel, "Net Kar Marjı — Çeyreklik (%)")
    roe        = _al(temel, "Özsermaye Karlılığı (ROE) — Yıllık")
    roa        = _al(temel, "Varlık Karlılığı (ROA) — Yıllık")
    roic       = _al(temel, "ROIC (%)")
    satis_y    = _al(temel, "Satış Büyümesi — Yıllık (%)")
    kar_y      = _al(temel, "Net Kar Büyümesi — Yıllık (%)")
    satis_yoy  = _al(temel, "Satış Büyümesi — YoY (%)")
    satis_qoq  = _al(temel, "Satış Büyümesi — QoQ (%)")
    cari       = _al(temel, "Cari Oran")
    de         = _al(temel, "Borç / Özsermaye (D/E)")
    net_borc_f = _al(temel, "Net Borç / FAVÖK")
    faiz_kar   = _al(temel, "Faiz Karşılama Oranı")
    fcf_get    = _al(temel, "FCF Getirisi (%)")
    fcf_kar    = _al(temel, "FCF / Net Kar")
    temettu    = _al(temel, "Temettü Verimi (%)")
    sektor     = _al(temel, "Firma Sektörü")
    fiyat      = _al(temel, "Fiyat")

    ema_ozet = "N/A"
    try:
        ema_str = teknik.get("EMA (Üstel)", "")
        ema_dict = {}
        for p in ema_str.split("|"):
            p = p.strip()
            if ":" in p and "g" in p:
                k, v = p.split(":", 1)
                gun = int(k.strip().replace("g", ""))
                ema_dict[gun] = float(v.strip())
        if ema_dict and fiyat != "N/A":
            uzerin = sum(1 for v in ema_dict.values() if float(fiyat) > v)
            ema_ozet = f"Fiyat {uzerin}/{len(ema_dict)} EMA'nın üzerinde"
    except:
        pass

    return f"""HİSSE: {hisse_kodu} | Sektör: {sektor} | Fiyat: {fiyat}

=== DEĞERLEME ===
F/K: {fk} | PD/DD: {pddd} | FD/FAVÖK: {fd_favk} | PEG: {peg} | F/S: {fs}

=== KARLILIK ===
Net Kar Marjı Y/Q: {net_mar_y}% / {net_mar_q}% | Brüt Marj: {brut_mar_y}% | FAVÖK Marjı: {favk_mar_y}%
ROE: {roe}% | ROA: {roa}% | ROIC: {roic}%

=== BÜYÜME ===
Satış Yıllık: {satis_y}% | Net Kar Yıllık: {kar_y}% | YoY: {satis_yoy}% | QoQ: {satis_qoq}%

=== BORÇ & LİKİDİTE ===
Cari Oran: {cari} | D/E: {de} | Net Borç/FAVÖK: {net_borc_f} | Faiz Karşılama: {faiz_kar}

=== NAKİT AKIŞI ===
FCF Getirisi: {fcf_get}% | FCF/Net Kar: {fcf_kar} | Temettü: {temettu}%

=== TEKNİK ===
RSI: {_rsi(_al(teknik, "RSI (14)", varsayilan="50"))} | Divergence: {_al(teknik, "RSI Divergence", varsayilan="Yok")}
Stoch RSI: {_al(teknik, "Stoch RSI (K / D)")} | MACD: {_al(teknik, "MACD (12,26,9)")}
ADX: {_al(teknik, "ADX (14) Trend Gücü")} | CMF: {_al(teknik, "CMF (20) Para Akışı")}
Bollinger: {_al(teknik, "Bollinger Bantları")} | BB %B: {_al(teknik, "BB %B")}
Ichimoku: {_al(teknik, "Ichimoku Bulut")} | T/K: {_al(teknik, "Ichimoku (Tenkan/Kijun)")}
Supertrend: {_al(teknik, "Supertrend (3,10)")} | AlphaTrend: {_al(teknik, "AlphaTrend (1,14)")}
Momentum: {_al(teknik, "Momentum (10)")} | RVOL: {_al(teknik, "Göreceli Hacim (RVOL)")}
Pivot: {_al(teknik, "Pivot (Geleneksel)")}
EMA: {ema_ozet}""".strip()


def ai_analist_yorumu(hisse_kodu: str, temel_veriler: dict, teknik_veriler: dict) -> str:
    baglam = _veri_ozeti_olustur(hisse_kodu, temel_veriler, teknik_veriler)
    prompt = f"{hisse_kodu} için verileri analiz et ve raporu hazırla:\n\n{baglam}"

    # ── 1. Gemini (google-genai SDK) ─────────────────────────────────────────
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
            print(f"[Gemini hata] {e} — Groq'a geçiliyor")

    # ── 2. Groq / Llama 3.3 70B ─────────────────────────────────────────────
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            yanit = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=1500,
                temperature=0.3,
                messages=[
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

    return "❌ API key tanımlı değil. GEMINI_API_KEY veya GROQ_API_KEY gerekli."


if __name__ == "__main__":
    from temel_analiz  import temel_analiz_yap
    from teknik_analiz import teknik_analiz_yap
    hisse = "ASELS.IS"
    print("Veriler çekiliyor...")
    t  = temel_analiz_yap(hisse)
    tk = teknik_analiz_yap(hisse)
    print(ai_analist_yorumu(hisse, t, tk))
