import os
from groq import Groq

SISTEM_PROMPTU = """Sen deneyimli bir Türk sermaye piyasaları analistissin. BIST hisseleri ve uluslararası piyasalar konusunda derin bilgin var. Görevin: sana verilen ham finansal ve teknik verileri yorumlayarak kurumsal kalitede, derinlikli bir Türkçe analist raporu hazırlamak.

RAPOR YAPISI (bu sırayı koru, her bölümü detaylı yaz):

1. ÖZET GÖRÜŞ
Şu etiketlerden birini seç ve KALIN yaz: GÜÇLÜ ALIM / ALIM / NÖTR / SATIM / GÜÇLÜ SATIM
Ardından 3-4 cümleyle: neden bu etiketi seçtiğini, hissenin genel durumunu ve yatırımcının dikkat etmesi gereken en kritik noktayı açıkla.

2. TEMEL ANALİZ

Değerleme:
- F/K, PD/DD, FD/FAVÖK rakamlarını sektör ortalamasıyla MUTLAKA karşılaştır. Örn: "F/K 42 ile sektör ortalaması olan 18'in 2.3 katı — prim ne kadar haklı?"
- Analist hedef fiyatı varsa mevcut fiyatla karşılaştır: "Konsensüs 362 TL hedefte, mevcut 280 TL'den %29 potansiyel sunuyor"
- Değerleme pahalı görünüyorsa bunu destekleyen veya çürüten büyüme/karlılık argümanı yaz

Büyüme ve Karlılık:
- Yıllık ve çeyreklik büyüme hızlarını değerlendir, trend ivmeleniyor mu yavaşlıyor mu?
- FAVÖK marjı, net kar marjı, ROE ve ROIC birlikte değerlendir
- "Bu marj seviyesi sektörde iyi/kötü/ortalama çünkü..." şeklinde bağlam ver

Bilanço Kalitesi:
- Borç yapısını yorumla: Net Borç/FAVÖK, faiz karşılama oranı
- FCF kalitesi: Net kara oranla FCF ne söylüyor? (FCF/Net Kar > 1 güçlü nakit)
- Cari oran ve likidite yeterliliği

3. TEKNİK ANALİZ

Trend Durumu:
- Supertrend, AlphaTrend ve EMA pozisyonunu sentezle — hepsi aynı yönü gösteriyor mu yoksa çelişiyor mu? Çelişiyorsa hangisi daha ağırlıklı?
- Ichimoku bulut durumunu yorumla

Momentum ve Sinyal:
- RSI seviyesi: aşırı alım/satım değil mi, divergence var mı?
- MACD histogram yönü (artıyor/azalıyor) momentum hakkında ne söylüyor?
- Stoch RSI K/D kesişimi yakın mı?

Hacim ve Para Akışı:
- RVOL normalin üstündeyse bunu yorumla (kurumsal ilgi mi, panik mi?)
- CMF pozitif/negatif: akıllı para giriyor mu çıkıyor mu?

Kritik Fiyat Seviyeleri:
- Pivot destek/direnç seviyelerini somut yaz: "310 kritik destek, kırılırsa 298 görülebilir"
- Bollinger bantlarına göre fiyat nerede?

4. GÜÇLÜ YÖNLER (3-5 madde, her biri somut rakamla desteklenmiş)

5. ZAYIF YÖNLER ve RİSKLER (3-5 madde, her biri somut rakamla desteklenmiş)

6. SENARYO ANALİZİ
- Olumlu senaryo: Hangi koşullar gerçekleşirse hisse yukarı kırabilir?
- Olumsuz senaryo: Hangi riskler fiyatı baskı altına alabilir?
- İzlenmesi gereken kritik tetikleyiciler (bilanço tarihi, sektörel gelişme vb.)

7. YATIRIMCI NOTU
Kısa bir kapanış: bu hisse hangi profildeki yatırımcıya uygun? (uzun vade/kısa vade, risk toleransı)
Son satır daima: "Bu rapor yatırım tavsiyesi değildir."

YAZIM KURALLARI:
- Her iddiayı somut rakamla destekle: "güçlü büyüme" değil "satışlar %47 arttı"
- Sektör karşılaştırması varsa MUTLAKA kullan
- N/A olan verileri yoksay ama eksikliği gerekirse belirt
- Çelişkili sinyalleri görmezden gelme, "teknik görünüm karışık: X yükselen trende işaret ederken Y düşen trende işaret ediyor" şeklinde yaz
- Markdown KULLANMA: **, *, #, _ karakterleri yasak. Sadece düz metin."""


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
        except Exception:
            return 50.0

    def _fmt(v, suffix=""):
        if v == "N/A":
            return "N/A"
        try:
            f = float(v)
            if abs(f) >= 1_000_000_000_000:
                return f"{f/1e12:.2f}T{suffix}"
            if abs(f) >= 1_000_000_000:
                return f"{f/1e9:.2f}B{suffix}"
            if abs(f) >= 1_000_000:
                return f"{f/1e6:.2f}M{suffix}"
            return f"{f:,.2f}{suffix}"
        except Exception:
            return str(v)

    # Temel veriler
    fk         = _al(temel, "F/K (Günlük)", "F/K (Hesaplanan)")
    pddd       = _al(temel, "PD/DD (Günlük)", "PD/DD (Hesaplanan)")
    fd_favk    = _al(temel, "FD/FAVÖK (Günlük)", "EV/EBITDA (Hesaplanan)")
    peg        = _al(temel, "PEG Oranı (Hesaplanan)", "PEG Oranı (Günlük)")
    fs         = _al(temel, "F/S (Fiyat/Satış)")
    net_mar_y  = _al(temel, "Net Kar Marjı — Yıllık (%)")
    brut_mar_y = _al(temel, "Brüt Kar Marjı — Yıllık (%)")
    favk_mar_y = _al(temel, "FAVÖK Marjı — Yıllık (%)")
    net_mar_q  = _al(temel, "Net Kar Marjı — Çeyreklik (%)")
    isle_mar_y = _al(temel, "İşletme Kar Marjı — Yıllık (%)")
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
    piyasa_d   = _al(temel, "Piyasa Değeri")
    beta       = _al(temel, "BETA (Manuel 1Y)", "BETA (yFinance)")

    # Ham değerler (büyüklük göstergesi için)
    satis_ham  = _al(temel, "_Satış — Yıllık")
    kar_ham    = _al(temel, "_Net Kar — Yıllık")
    favok_ham  = _al(temel, "_FAVÖK — Yıllık")
    fcf_ham    = _al(temel, "_FCF")

    # borsapy verileri
    fiili_dolasim = _al(temel, "Fiili Dolaşım (%)")
    yabanci_oran  = _al(temel, "Yabancı Oranı (%)")
    analist_ort   = _al(temel, "Analist Hedef — Ort (TL)")
    analist_min   = _al(temel, "Analist Hedef — Min (TL)")
    analist_maks  = _al(temel, "Analist Hedef — Maks (TL)")
    analist_n     = _al(temel, "Analist Sayısı")
    ana_ortaklar  = _al(temel, "Ana Ortaklar")
    sektor_fk     = _al(temel, "Sektör Ort. F/K")
    sektor_pddd   = _al(temel, "Sektör Ort. PD/DD")
    sektor_n      = _al(temel, f"Sektör ({sektor}) — Hisse Sayısı")
    veri_dogrulama = _al(temel, "⚠️ Veri Tutarsızlığı", "✅ Veri Doğrulaması")

    # Analist potansiyel hesapla
    analist_potansiyel = "N/A"
    try:
        if analist_ort != "N/A" and fiyat != "N/A":
            pot = (float(analist_ort) - float(fiyat)) / float(fiyat) * 100
            analist_potansiyel = f"%{pot:+.1f}"
    except Exception:
        pass

    # Sektör karşılaştırma yorumu
    sektor_yorum = ""
    if sektor_fk != "N/A" and fk != "N/A":
        try:
            kat = float(fk) / float(sektor_fk)
            sektor_yorum += f"\nF/K sektör karşılaştırması: {fk} (hisse) vs {sektor_fk} (sektör ort., n={sektor_n}) — {kat:.1f}x"
        except Exception:
            pass
    if sektor_pddd != "N/A" and pddd != "N/A":
        try:
            kat = float(pddd) / float(sektor_pddd)
            sektor_yorum += f"\nPD/DD sektör karşılaştırması: {pddd} (hisse) vs {sektor_pddd} (sektör ort.) — {kat:.1f}x"
        except Exception:
            pass

    # EMA pozisyon özeti
    ema_ozet = "N/A"
    try:
        ema_str = teknik.get("EMA (Üstel)", "")
        ema_dict = {}
        for p in ema_str.split("|"):
            p = p.strip()
            if ":" in p and "g" in p:
                k, val = p.split(":", 1)
                gun = int(k.strip().replace("g", ""))
                ema_dict[gun] = float(val.strip())
        if ema_dict and fiyat != "N/A":
            uzerin = [(g, v) for g, v in sorted(ema_dict.items()) if float(fiyat) > v]
            altinda = [(g, v) for g, v in sorted(ema_dict.items()) if float(fiyat) <= v]
            ema_ozet = f"Fiyat {len(uzerin)}/{len(ema_dict)} EMA'nın üzerinde"
            if uzerin:
                ema_ozet += f" (en yakın üst: {uzerin[-1][0]}g={uzerin[-1][1]:.1f})"
            if altinda:
                ema_ozet += f" | ilk direnç EMA: {altinda[0][0]}g={altinda[0][1]:.1f}"
    except Exception:
        pass

    return f"""=== HİSSE BİLGİSİ ===
Hisse: {hisse_kodu} | Sektör: {sektor} | Fiyat: {fiyat} TL | Piyasa Değeri: {_fmt(piyasa_d)}
Fiili Dolaşım: {fiili_dolasim}% | Yabancı Oranı: {yabanci_oran}% | Beta(1Y): {beta}
Ana Ortaklar: {ana_ortaklar}
Veri Doğrulama: {veri_dogrulama}

=== DEĞERLEME ===
F/K: {fk} | PD/DD: {pddd} | FD/FAVÖK: {fd_favk} | PEG: {peg} | F/S: {fs}{sektor_yorum}
Analist Konsensüs: {analist_ort} TL hedef ({analist_n} analist) | Min: {analist_min} | Maks: {analist_maks} | Potansiyel: {analist_potansiyel}

=== BÜYÜME ===
Satış Büyümesi — Yıllık: {satis_y}% | Net Kar Büyümesi: {kar_y}%
Satış YoY (son çeyrek): {satis_yoy}% | QoQ: {satis_qoq}%
Finansal Büyüklükler: Satış={_fmt(satis_ham)} | Net Kar={_fmt(kar_ham)} | FAVÖK={_fmt(favok_ham)} | FCF={_fmt(fcf_ham)}

=== KARLILIK ===
Net Kar Marjı (Y/Q): {net_mar_y}% / {net_mar_q}% | Brüt: {brut_mar_y}% | İşletme: {isle_mar_y}% | FAVÖK: {favk_mar_y}%
ROE: {roe}% | ROA: {roa}% | ROIC: {roic}%

=== BORÇ & LİKİDİTE ===
D/E: {de} | Net Borç/FAVÖK: {net_borc_f} | Faiz Karşılama: {faiz_kar} | Cari Oran: {cari}

=== NAKİT AKIŞI ===
FCF Getirisi: {fcf_get}% | FCF/Net Kar: {fcf_kar} | Temettü: {temettu}%

=== TEKNİK ANALİZ ===
RSI(14): {_rsi(_al(teknik, "RSI (14)", varsayilan="50"))} | RSI Divergence: {_al(teknik, "RSI Divergence", varsayilan="Yok")}
Stoch RSI (K/D): {_al(teknik, "Stoch RSI (K / D)")} | MACD: {_al(teknik, "MACD (12,26,9)")}
ADX: {_al(teknik, "ADX (14) Trend Gücü")} | CMF: {_al(teknik, "CMF (20) Para Akışı")} | RVOL: {_al(teknik, "Göreceli Hacim (RVOL)")}
Bollinger: {_al(teknik, "Bollinger Bantları")} | BB%B: {_al(teknik, "BB %B")}
Ichimoku: {_al(teknik, "Ichimoku Bulut")} | T/K: {_al(teknik, "Ichimoku (Tenkan/Kijun)")}
Supertrend(3,10): {_al(teknik, "Supertrend (3,10)")} | AlphaTrend(1,14): {_al(teknik, "AlphaTrend (1,14)")}
Momentum(10): {_al(teknik, "Momentum (10)")} | ATR(14): {_al(teknik, "ATR (14) Volatilite")}
Pivot: {_al(teknik, "Pivot (Geleneksel)")}
EMA Pozisyon: {ema_ozet}"""

    # Finnhub haberleri varsa ekle
    haber_ozeti = temel.get("__haberler__", "")
    if haber_ozeti:
        sonuc += f"\n\n{haber_ozeti}"

    return sonuc.strip()


def _ai_gonder(prompt: str, sistem_promptu: str = None) -> str:
    """Gemini → Groq fallback ile AI yanıtı üretir."""
    sp = sistem_promptu or SISTEM_PROMPTU

    # 1. Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            from google.genai import types
            client_g = genai.Client(api_key=gemini_key)
            response = client_g.models.generate_content(
                model="models/gemini-2.5-flash",
                config=types.GenerateContentConfig(
                    system_instruction=sp,
                    temperature=0.4,
                    max_output_tokens=2500,
                    response_mime_type="text/plain",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
                contents=prompt,
            )
            return "Gemini Analiz:\n\n" + response.text
        except Exception as e:
            print(f"[Gemini hata] {e} — Groq'a geçiliyor")

    # 2. Groq
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            yanit = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=2500,
                temperature=0.4,
                messages=[
                    {"role": "system", "content": sp},
                    {"role": "user",   "content": prompt}
                ]
            )
            return "Llama 3.3 Analiz:\n\n" + yanit.choices[0].message.content
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                return "Groq rate limit asildi, 1 dakika sonra tekrar deneyin."
            return f"Groq hatasi: {err}"

    return "API key tanimli degil. GEMINI_API_KEY veya GROQ_API_KEY gerekli."


def ai_analist_yorumu(hisse_kodu: str, temel_veriler: dict, teknik_veriler: dict) -> str:
    baglam = _veri_ozeti_olustur(hisse_kodu, temel_veriler, teknik_veriler)
    prompt = f"{hisse_kodu} hissesi için aşağıdaki verileri analiz et ve detaylı rapor hazırla. Her bölümü eksiksiz doldur, somut rakamlar ve sektör karşılaştırmaları kullan:\n\n{baglam}"
    return _ai_gonder(prompt)


# ─────────────────────────────────────────────
#  PİYASA AI YORUMU (kripto / döviz / emtia)
# ─────────────────────────────────────────────

PIYASA_SISTEM_PROMPTU = """Sen deneyimli bir finansal analistsin. Kripto para, döviz ve emtia piyasalarında derinlemesine bilgiye sahipsin.

Sana bir varlığın piyasa bilgisi ve teknik analiz verileri verilecek. Bu verileri sentezleyerek kurumsal kalitede, Türkçe, rakamlara dayalı bir analiz raporu yaz.

RAPOR YAPISI:

1. ÖZET GÖRÜŞ
Şu etiketlerden birini seç: GÜÇLÜ ALIM / ALIM / NÖTR / SATIM / GÜÇLÜ SATIM
3-4 cümleyle varlığın genel durumunu, ana trendin yönünü ve en kritik riski açıkla.

2. FİYAT ANALİZİ
- Mevcut fiyatı 52 haftalık yüksek/düşük ile karşılaştır. Yıllık, aylık, haftalık getiriyi yorumla.
- Döviz/emtia için: makroekonomik bağlamı ekle (enflasyon, merkez bankası politikası, arz/talep)
- Kripto için: piyasa döngüsü, BTC dominansı, on-chain bağlamı ekle

3. TEKNİK ANALİZ
Trend: Supertrend, AlphaTrend ve EMA pozisyonuna göre ana trend — hepsi aynı yönde mi çelişiyor mu?
Momentum: RSI seviyesi ve divergence, MACD histogram yönü, Stoch RSI durumu
Hacim & Para Akışı: RVOL ve CMF ne söylüyor?
Kritik Seviyeler: Pivot destek/direnç seviyelerini somut yaz. Bollinger bandı durumu.
Uyarılar: Trend değişim sinyali veya divergence varsa vurgula.

4. GÜÇLÜ YÖNLER (3-4 madde, rakamla destekle)
5. ZAYIF YÖNLER & RİSKLER (3-4 madde, rakamla destekle)

6. SENARYO ANALİZİ
Yükseliş senaryosu: Hangi koşullar gerçekleşirse yukarı kırabilir? Hedef seviyeler?
Düşüş senaryosu: Hangi riskler fiyatı aşağı çekebilir? Destek seviyeleri?

7. YATIRIMCI NOTU
Bu varlık hangi profildeki yatırımcıya uygun? Risk toleransı?
Son satır daima: "Bu rapor yatırım tavsiyesi değildir."

KURALLAR:
- Rakamları mutlaka kullan
- Varlık tipine göre bağlam ver (kripto volatile, döviz makro bağımlı, emtia arz/talep)
- Markdown KULLANMA: **, *, #, _ yasak. Sadece düz metin."""


def _piyasa_veri_ozeti(sembol: str, tip: str, piyasa: dict, teknik: dict) -> str:
    """Kripto/döviz/emtia için AI prompt özeti oluşturur."""

    def _al(d, *keys):
        for k in keys:
            v = d.get(k)
            if v is not None and v not in ("", "N/A", 0):
                return v
        return "N/A"

    # Piyasa bilgileri
    fiyat    = _al(piyasa, "Fiyat")
    degisim  = _al(piyasa, "Degisim (%)")
    aciklama = _al(piyasa, "Isim", "Aciklama", "Parite", sembol)

    # Getiriler
    getiri_satirlari = []
    for label in ["1 Hafta", "1 Ay", "3 Ay", "1 Yil"]:
        v = piyasa.get(f"Getiri ({label})")
        if v:
            getiri_satirlari.append(f"{label}: {v}")
    getiriler = " | ".join(getiri_satirlari) if getiri_satirlari else "N/A"

    # Kripto'ya özel
    ekstra = ""
    if tip == "kripto":
        piyasa_d  = _al(piyasa, "Piyasa Degeri")
        hacim     = _al(piyasa, "Hacim (24s)")
        dolasim   = _al(piyasa, "Dolasim Arzi")
        maks_arz  = _al(piyasa, "Maks Arz")
        ekstra = f"\nPiyasa Değeri: {piyasa_d} | 24s Hacim: {hacim}"
        ekstra += f"\nDolaşım Arzı: {dolasim} | Maks Arz: {maks_arz}"
    elif tip == "emtia":
        borsa = _al(piyasa, "Borsa")
        ekstra = f"\nBorsa: {borsa}"

    # Teknik indikatörler
    def _t(k):
        return teknik.get(k, "N/A")

    # EMA özeti
    ema_ozet = "N/A"
    try:
        ema_str = teknik.get("EMA (Üstel)", "")
        ema_dict = {}
        for p in ema_str.split("|"):
            p = p.strip()
            if ":" in p and "g" in p:
                k, val = p.split(":", 1)
                ema_dict[int(k.strip().replace("g",""))] = float(val.strip())
        if ema_dict:
            try:
                fiyat_f = float(str(fiyat).split()[0].replace(",",""))
                uzerin = sum(1 for v in ema_dict.values() if fiyat_f > v)
                ema_ozet = f"Fiyat {uzerin}/{len(ema_dict)} EMA'nın üzerinde"
            except Exception:
                ema_ozet = f"{len(ema_dict)} EMA hesaplandı"
    except Exception:
        pass

    tip_tr = {"kripto": "KRİPTO", "doviz": "DÖVİZ", "emtia": "EMTİA"}.get(tip, tip.upper())

    return f"""=== {tip_tr} BİLGİSİ ===
Sembol: {sembol} | Açıklama: {aciklama}
Fiyat: {fiyat} | Günlük Değişim: {degisim}{ekstra}
Dönemsel Getiri: {getiriler}

=== TEKNİK ANALİZ ===
RSI(14): {_t("RSI (14)")} | Divergence: {_t("RSI Divergence")}
Stoch RSI (K/D): {_t("Stoch RSI (K / D)")} | MACD: {_t("MACD (12,26,9)")}
ADX: {_t("ADX (14) Trend Gücü")} | CMF: {_t("CMF (20) Para Akışı")} | RVOL: {_t("Göreceli Hacim (RVOL)")}
Bollinger: {_t("Bollinger Bantları")} | BB%B: {_t("BB %B")}
Ichimoku: {_t("Ichimoku Bulut")} | T/K: {_t("Ichimoku (Tenkan/Kijun)")}
Supertrend(3,10): {_t("Supertrend (3,10)")} | AlphaTrend(1,14): {_t("AlphaTrend (1,14)")}
Momentum(10): {_t("Momentum (10)")} | ATR(14): {_t("ATR (14) Volatilite")}
Pivot: {_t("Pivot (Geleneksel)")}
EMA Pozisyon: {ema_ozet}""".strip()


def ai_piyasa_yorumu(sembol: str, tip: str, piyasa: dict, teknik: dict) -> str:
    """
    Kripto, döviz veya emtia için AI analiz yorumu üretir.
    tip: 'kripto' | 'doviz' | 'emtia'
    """
    tip_tr = {"kripto": "kripto para", "doviz": "döviz paritesi", "emtia": "emtia"}.get(tip, tip)
    baglam = _piyasa_veri_ozeti(sembol, tip, piyasa, teknik)
    prompt = (
        f"{sembol} {tip_tr} için aşağıdaki verileri analiz et ve detaylı rapor hazırla. "
        f"Teknik sinyalleri, fiyat seviyelerini ve makroekonomik bağlamı birlikte değerlendir:\n\n{baglam}"
    )
    return _ai_gonder(prompt, sistem_promptu=PIYASA_SISTEM_PROMPTU)


if __name__ == "__main__":
    from temel_analiz  import temel_analiz_yap
    from teknik_analiz import teknik_analiz_yap
    hisse = "ASELS.IS"
    print("Veriler cekiliyor...")
    t  = temel_analiz_yap(hisse)
    tk = teknik_analiz_yap(hisse)
    print(ai_analist_yorumu(hisse, t, tk))
