import os
import re
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot

from temel_analiz   import temel_analiz_yap
from teknik_analiz  import teknik_analiz_yap
from analist_motoru import ai_analist_yorumu, ai_piyasa_yorumu
from cache_yonetici import baslangic_temizligi
from piyasa_analiz  import (
    kripto_analiz, doviz_analiz, emtia_analiz,
    KRIPTO_LISTE, DOVIZ_LISTE, EMTIA_LISTE,
    KRIPTO_MAP, DOVIZ_MAP, EMTIA_MAP
)
from veri_motoru import (
    finnhub_haberler, finnhub_insider, finnhub_kazanc,
    reddit_trend, reddit_kripto_trend,
    coingecko_trending, alphavantage_fiyat,
    ai_icin_haber_ozeti, durum_raporu
)

# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN tanımlı değil.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
_son_istek: dict = {}
RATE_LIMIT_SANIYE = 15
TELEGRAM_LIMIT    = 4000

# ─────────────────────────────────────────────
#  HTML YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def h(text) -> str:
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def bold(text) -> str:
    return f"<b>{h(text)}</b>"

def code(text) -> str:
    return f"<code>{h(text)}</code>"

def pre(text) -> str:
    return f"<pre>{h(text)}</pre>"

def _fmt(v) -> str:
    if isinstance(v, float):
        if abs(v) >= 1e12: return f"{v/1e12:.2f}T"
        if abs(v) >= 1e9:  return f"{v/1e9:.2f}B"
        if abs(v) >= 1e6:  return f"{v/1e6:.2f}M"
        return f"{v:,.2f}"
    if isinstance(v, int):
        if abs(v) > 1e12: return f"{v/1e12:.2f}T"
        if abs(v) > 1e9:  return f"{v/1e9:.2f}B"
        if abs(v) > 1e6:  return f"{v/1e6:.2f}M"
    return str(v)

def _parcala(metin: str, limit: int = TELEGRAM_LIMIT) -> list:
    if len(metin) <= limit:
        return [metin]
    parcalar = []
    while len(metin) > limit:
        kesim = metin.rfind("</pre>", 0, limit)
        if kesim != -1:
            kesim += 6
        else:
            kesim = metin.rfind("\n", 0, limit) or limit
        parcalar.append(metin[:kesim])
        metin = metin[kesim:].lstrip("\n")
    if metin.strip():
        parcalar.append(metin)
    return parcalar

def _gonder(chat_id, mesaj_id, metin, duzenle=True):
    for i, parca in enumerate(_parcala(metin)):
        try:
            if i == 0 and duzenle:
                bot.edit_message_text(parca, chat_id=chat_id,
                    message_id=mesaj_id, parse_mode="HTML")
            else:
                bot.send_message(chat_id, parca, parse_mode="HTML")
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                bot.send_message(chat_id, parca, parse_mode="HTML")

# ─────────────────────────────────────────────
#  BLOK OLUŞTURUCUlar
# ─────────────────────────────────────────────

AYRAC = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"

def blok(baslik: str, emoji: str, satirlar: list) -> str:
    if not satirlar:
        return ""
    icerik_lst = []
    for s in satirlar:
        if isinstance(s, tuple):
            k, v = s
            v_str = _fmt(v)
            if not v_str or v_str in ("None","nan","0","0.00","N/A",""):
                continue
            icerik_lst.append(f"  {k:<32} {h(v_str)}")
        else:
            if str(s).strip():
                icerik_lst.append(f"  {h(str(s))}")
    if not icerik_lst:
        return ""
    icerik = "\n".join(icerik_lst)
    return f"\n{bold(emoji + ' ' + baslik)}\n<pre>{icerik}</pre>"

def temel_blok(baslik: str, emoji: str, veriler: dict, filtre) -> str:
    satirlar = []
    for k, v in veriler.items():
        if k.startswith("_") or not filtre(k):
            continue
        v_str = _fmt(v)
        if not v_str or v_str in ("None","nan","0","0.00","N/A",""):
            continue
        satirlar.append((k, v_str))
    return blok(baslik, emoji, satirlar)

def ma_blok(teknik: dict) -> str:
    satirlar = []
    for tip in ("SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"):
        if tip in teknik:
            kisalt = tip.split()[0]
            deger  = teknik[tip]
            periyo_parcalar = [p.strip() for p in deger.split("|")]
            satirlar.append(f"  {kisalt}:")
            satirlar.append("    " + "  ".join(periyo_parcalar[:7]))
            if len(periyo_parcalar) > 7:
                satirlar.append("    " + "  ".join(periyo_parcalar[7:]))
    if not satirlar:
        return ""
    icerik = "\n".join(satirlar)
    return f"\n{bold('🌊 HAREKETLİ ORTALAMALAR')}\n<pre>{icerik}</pre>"

# ─────────────────────────────────────────────
#  TEMEL ANALİZ GRUPLARI
# ─────────────────────────────────────────────

TEMEL_GRUPLAR = [
    ("Genel",       "ℹ️",  lambda k: k in (
        "Firma Sektörü","Çalışan Sayısı","Para Birimi","Borsa",
        "Bilanço Dönemi","Son Çeyrek Dönemi")),
    ("Piyasa",      "💹", lambda k: k in (
        "Fiyat","Piyasa Değeri","F/K (Günlük)","PD/DD (Günlük)",
        "FD/FAVÖK (Günlük)","BETA (yFinance)","PEG Oranı (Günlük)",
        "Fiili Dolaşım (%)","Yabancı Oranı (%)",
        "⚠️ Veri Tutarsızlığı","✅ Veri Doğrulaması")),
    ("Analist",     "🎯", lambda k: k in (
        "Analist Hedef — Ort (TL)","Analist Hedef — Med (TL)",
        "Analist Hedef — Min (TL)","Analist Hedef — Maks (TL)",
        "Analist Sayısı","Ana Ortaklar")),
    ("Sektör",      "📊", lambda k: "Sektör" in k),
    ("Değerleme",   "🏷",  lambda k: k in (
        "F/K (Hesaplanan)","PD/DD (Hesaplanan)","F/S (Fiyat/Satış)",
        "EV/EBITDA (Hesaplanan)","EV/EBIT","EV/Sales","PEG Oranı (Hesaplanan)")),
    ("Karlılık Y",  "📈", lambda k: ("Yıllık" in k and any(
        x in k for x in ["Marjı","Karlılık","ROE","ROA","ROIC"])) or k=="ROIC (%)"),
    ("Karlılık Ç",  "📊", lambda k: "Çeyreklik" in k and any(
        x in k for x in ["Marjı","Karlılık"])),
    ("Büyüme",      "🚀", lambda k: "Büyüme" in k or k=="EPS Büyümesi — Yıllık (%)"),
    ("Likidite",    "💧", lambda k: k in (
        "Cari Oran","Likidite Oranı (Hızlı)","Nakit Oranı")),
    ("Borç",        "🏦", lambda k: k in (
        "Borç / Özsermaye (D/E)","Finansal Borç / Özsermaye (%)",
        "Net Borç / FAVÖK","Faiz Karşılama Oranı","Finansal Borç / Varlık (%)")),
    ("Faaliyet",    "⚙️",  lambda k: k in (
        "Varlık Devir Hızı","Stok Devir Hızı","Alacak Devir Hızı",
        "Stok Günü (DSI)","Alacak Günü (DSO)")),
    ("Nakit Akışı", "💵", lambda k: k in (
        "FCF (Serbest Nakit Akışı)","FCF Getirisi (%)","FCF / Net Kar",
        "Temettü Verimi (%)","Temettü Ödeme Oranı (%)")),
]

# ─────────────────────────────────────────────
#  SEMBOL NORMALIZE
# ─────────────────────────────────────────────

_BILINEN_UZANTILAR = {
    ".IS",".L",".PA",".DE",".MI",".AS",".BR",".MC",".SW",
    ".HK",".T",".SS",".SZ",".KS",".KQ",".AX",".TO",".V",
    ".SA",".MX",".NS",".BO",
}
_TICKER_CACHE: dict = {}

# Bilinen BIST hisseleri — yFinance sorgusu yapmadan direkt .IS ekle
_BIST_HISSELER = {
    "ASELS","THYAO","TUPRS","GARAN","AKBNK","YKBNK","ISCTR","HALKB","VAKBN",
    "KCHOL","SAHOL","EREGL","BIMAS","MGROS","SISE","ARCLK","TOASO","FROTO",
    "PGSUS","TAVHL","TKFEN","ENKAI","KOZAL","KRDMD","PETKM","AGHOL","DOHOL",
    "OTKAR","TTKOM","TCELL","EKGYO","ISGYO","ALKIM","AKSEN","ZOREN","SOKM",
    "MAVI","LOGO","NETAS","OYAKC","CEMTS","BRISA","ULKER","BAGFS","GUBRF",
    "HEKTS","KLNMA","INDES","DENGE","VESTL","KAREL","ADEL","AEFES","ASUZU",
    "BANVT","BRSAN","BUCIM","CIMSA","DOAS","DYOBY","EGEEN","EGSER","GLYHO",
    "GOLTS","GOODY","HURGZ","IZMDC","JANTS","KARSN","KATMR","KENT","KERVT",
    "KIPA","KONTR","KONYA","KOPOL","KORDS","KUTPO","LKMNH","MAALT","MEPET",
    "MNDRS","MRDIN","NTTUR","NUHCM","PARSN","PENGD","PRKAB","PRKME","PRZMA",
    "PTOFS","RYSAS","SELGD","SILVR","SKBNK","SMART","SNGYO","TATGD","TSKB",
    "TTRAK","TURSG","UNYEC","USAK","VKFYO","YKFIN","YPKRK","CCOLA","SASA",
    "KRDMA","KRDMB","KCAER","ISBIR","SARKY","ENJSA","TKFEN","CLEBI","AKCNS",
    "AKGRT","AKSA","ALBRK","CEMAS","CMBTN","CMENT","CUSAN","DEVA","DNISI",
    "ECZYT","EKGYO","EMKEL","ENKAI","EPLAS","ERBOS","ERSU","FONET","GARFA",
    "GEDIK","GENIL","GENTS","GEREL","GLBMD","GOKNR","GOZDE","GRSEL","GSRAY",
    "GULER","HATEK","HEDEF","HLGYO","HUBVC","HUNER","IHEVA","IHLAS","IMASM",
    "ISFIN","ISGSY","ISMEN","KAYSE","KARTN","KAPLM","KLKIM","KLSER","KNFRT",
    "KONKA","KRONT","KRSTL","LINK","LUKSK","MAKTK","MANAS","MARKA","MEDTR",
    "MEGAP","MERKO","MEYSU","MMCAS","MOBTL","MNDTR","MSGYO","NATEN","NETCD",
    "NTHOL","NUGYO","ODAS","ONCSM","ORGE","ORMA","OSMEN","OTTO","OYYAT",
    "OYLUM","PAHOL","PAMEL","PNLSN","PRDGS","PEKGY","PKART","PLTUR","POLHO",
    "POLTK","PRVAK","QNBFK","RALYH","RNPOL","RYGYO","RODRG","ROYAL","RTALB",
    "RUBNS","SANKO","SANEL","SNICA","SANFM","SAMAT","SARKY","SAYAS","SDTTR",
    "SEKUR","SELVA","SELEC","SRVGY","SEYKM","SMRTG","SODSN","SOKE","SUMAS",
    "SUNTK","SUWEN","SKTAS","SNPAM","TARKM","TATGD","TATEN","TEKTU","TKNSA",
    "TMPOL","TRGYO","TRMET","TLMAN","TSPOR","TDGYO","TSGYO","TUKAS","TRCAS",
    "TUREX","TRILC","TUCLK","TMSN","PRKAB","TBORG","TURGG","KLNMA","UCAYM",
    "ULUFA","ULUSE","ULUUN","UMPAS","VAKFA","VAKFN","VKGYO","VAKKO","VANGD",
    "VBTYZ","VERUS","VESBE","YAPRK","YATAS","YYLGD","YAYLA","YGGYO","YEOTK",
    "YGYO","YYAPI","YESIL","YONGA","YKSLN","YUNSA","YBTAS","ZGYO","ZEDUR",
    "ZERGY","ZRGYO","CELHA","OZKGY","OZGYO","UNLU","IDGYO","INTEM","ISDMR",
    "SEKFK","SEGYO","SKYMD","OBAMS","NTHOL",
}

def _normalize_ticker(ticker: str) -> str:
    """
    Ticker sembolünü yFinance formatına dönüştürür.
    Önce bilinen BIST listesine bakar (hızlı, API çağrısı yok).
    Bilinmeyen semboller için yFinance ile doğrulama yapar.
    """
    import yfinance as yf
    ticker = ticker.upper().strip()

    # Zaten uzantılı ise direkt dön
    for uzanti in _BILINEN_UZANTILAR:
        if ticker.endswith(uzanti):
            return ticker

    # Cache'de varsa dön
    if ticker in _TICKER_CACHE:
        return _TICKER_CACHE[ticker]

    # Bilinen BIST hissesi ise direkt .IS ekle (yFinance API çağrısı yok)
    if ticker in _BIST_HISSELER:
        sonuc = ticker + ".IS"
        _TICKER_CACHE[ticker] = sonuc
        return sonuc

    # Bilinmeyen sembol: önce direkt dene (ABD hissesi olabilir)
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if not hist.empty:
            _TICKER_CACHE[ticker] = ticker
            return ticker
    except Exception:
        pass

    # Sonra .IS dene
    ticker_is = ticker + ".IS"
    try:
        hist = yf.Ticker(ticker_is).history(period="5d")
        if not hist.empty:
            _TICKER_CACHE[ticker] = ticker_is
            return ticker_is
    except Exception:
        pass

    # Varsayılan
    _TICKER_CACHE[ticker] = ticker
    return ticker


def rate_limit_kontrol(user_id: int) -> int:
    son = _son_istek.get(user_id)
    if son is None:
        return 0
    gecen = (datetime.now() - son).total_seconds()
    return max(0, int(RATE_LIMIT_SANIYE - gecen))

# ─────────────────────────────────────────────
#  PİYASA EMOJİ/BAŞLIK
# ─────────────────────────────────────────────

_TIP_EMOJI  = {"kripto":"₿","doviz":"💱","emtia":"🏭"}
_TIP_BASLIK = {"kripto":"KRİPTO","doviz":"DÖVİZ","emtia":"EMTİA"}

GENEL_ANAHTARLAR = {
    "kripto": ["Isim","Para Birimi","Fiyat","Degisim (%)","Degisim (24s %)",
               "Degisim (7g %)","Degisim (30g %)","Piyasa Degeri","Hacim (24s)",
               "Dolasim Arzi","Maks Arz","ATH","ATH Dusus (%)","Siralama"],
    "doviz":  ["Parite","Aciklama","Fiyat","Degisim (%)",
               "Getiri (1 Hafta)","Getiri (1 Ay)","Getiri (3 Ay)","Getiri (1 Yil)"],
    "emtia":  ["Aciklama","Para Birimi","Borsa","Fiyat","Degisim (%)",
               "Getiri (1 Hafta)","Getiri (1 Ay)","Getiri (3 Ay)","Getiri (1 Yil)"],
}

# ─────────────────────────────────────────────
#  KOMUTLAR
# ─────────────────────────────────────────────

@bot.message_handler(commands=["start","yardim"])
def komut_yardim(message):
    metin = (
        f"📈 {bold('Finans Asistanı')}\n"
        f"<i>Türkiye · Dünya · Kripto · Döviz · Emtia</i>\n\n"

        f"🇹🇷 {bold('BIST Hisseleri')}\n"
        f"{code('/analiz TUPRS')}  Temel + Teknik\n"
        f"{code('/temel  THYAO')}  Yalnızca temel\n"
        f"{code('/teknik ASELS')}  Yalnızca teknik\n"
        f"{code('/ai     ASELS')}  🤖 AI Yorumu\n\n"

        f"🌍 {bold('Yabancı Hisseler')}\n"
        f"{code('/analiz AAPL  ')}  ABD (direkt sembol)\n"
        f"{code('/analiz SHEL.L')}  Londra  (.L)\n"
        f"{code('/analiz SAP.DE')}  Frankfurt (.DE)\n"
        f"{code('/ai     NVDA  ')}  AI Yorumu\n\n"

        f"₿ {bold('Kripto')}\n"
        f"{code('/kripto BTC   ')}  Bitcoin (USD)\n"
        f"{code('/kripto ETHTRY')}  Ethereum (TRY)\n"
        f"{code('/ai     BTC   ')}  AI Kripto Yorumu\n"
        f"{code('/kripto liste ')}  Tüm semboller\n\n"

        f"💱 {bold('Döviz')}\n"
        f"{code('/doviz USDTRY ')}  Dolar/TL\n"
        f"{code('/doviz EURUSD ')}  Euro/Dolar\n"
        f"{code('/ai    USDTRY ')}  AI Döviz Yorumu\n"
        f"{code('/doviz liste  ')}  Tüm pariteler\n\n"

        f"🏭 {bold('Emtia')}\n"
        f"{code('/emtia ALTIN  ')}  Altın vadeli\n"
        f"{code('/emtia PETROL ')}  Ham petrol\n"
        f"{code('/ai    ALTIN  ')}  AI Emtia Yorumu\n"
        f"{code('/emtia liste  ')}  Tüm emtialar\n\n"

        f"📰 {bold('Haberler & Insider')}\n"
        f"{code('/haber  AAPL  ')}  Son haberler (Finnhub/yFinance/KAP)\n"
        f"{code('/insider AAPL ')}  İçeriden alım/satım\n"
        f"{code('/trend        ')}  Reddit WSB hisse trend\n"
        f"{code('/trend kripto ')}  CoinGecko + Reddit kripto trend\n\n"

        f"🔧 {bold('Sistem')}\n"
        f"{code('/durum        ')}  API bağlantı durumu\n\n"

        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"💡 BIST'te {code('.IS')} otomatik eklenir\n"
        f"⏱ Sorgular arası min {bold(str(RATE_LIMIT_SANIYE))} saniye"
    )
    bot.reply_to(message, metin, parse_mode="HTML")


@bot.message_handler(commands=["analiz","temel","teknik","ai"])
def komut_analiz(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            f"⚠️ Sembol belirtin. Örnek: {code('/analiz ASELS')} veya {code('/ai BTC')}",
            parse_mode="HTML")
        return

    girdi   = parcalar[1].upper().strip()
    komut   = parcalar[0].lstrip("/").lower()
    user_id = message.from_user.id

    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ Lütfen {bold(str(bekleme))} saniye bekleyin.",
            parse_mode="HTML")
        return
    _son_istek[user_id] = datetime.now()

    # Piyasa tipi kontrolü (kripto/döviz/emtia)
    piyasa_tip = None
    if girdi in KRIPTO_MAP or girdi.endswith("-USD") or girdi.endswith("-TRY"):
        piyasa_tip = "kripto"
    elif girdi in DOVIZ_MAP or girdi.endswith("=X"):
        piyasa_tip = "doviz"
    elif girdi in EMTIA_MAP or girdi.endswith("=F"):
        piyasa_tip = "emtia"

    if piyasa_tip:
        if komut == "temel":
            bot.reply_to(message,
                f"ℹ️ {bold(girdi)} için temel finansal veri yok.\n"
                f"Bunun yerine: {code(f'/{piyasa_tip} {girdi}')}",
                parse_mode="HTML")
            return
        bekle_msg = bot.reply_to(message,
            f"⏳ {bold(girdi)} analiz ediliyor...", parse_mode="HTML")
        hedef = _piyasa_ai_isle if komut == "ai" else _piyasa_isle
        threading.Thread(target=hedef,
            args=(message.chat.id, bekle_msg.message_id, girdi, piyasa_tip),
            daemon=True).start()
        return

    # Hisse analizi — normalize_ticker burada çağrılıyor
    hisse_kodu = _normalize_ticker(girdi)
    bekle_msg = bot.reply_to(message,
        f"⏳ {bold(hisse_kodu)} verileri işleniyor...", parse_mode="HTML")
    threading.Thread(target=_analiz_isle,
        args=(message.chat.id, bekle_msg.message_id, hisse_kodu, komut),
        daemon=True).start()


@bot.message_handler(commands=["kripto"])
def komut_kripto(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            f"⚠️ Örnek: {code('/kripto BTC')} veya {code('/kripto liste')}",
            parse_mode="HTML")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message,
            f"₿ {bold('Desteklenen Kriptolar')}\n{code(KRIPTO_LISTE)}",
            parse_mode="HTML")
        return
    _piyasa_komut(message, girdi, "kripto")


@bot.message_handler(commands=["doviz"])
def komut_doviz(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            f"⚠️ Örnek: {code('/doviz USDTRY')} veya {code('/doviz liste')}",
            parse_mode="HTML")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message,
            f"💱 {bold('Desteklenen Pariteler')}\n{code(DOVIZ_LISTE)}",
            parse_mode="HTML")
        return
    _piyasa_komut(message, girdi, "doviz")


@bot.message_handler(commands=["emtia"])
def komut_emtia(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            f"⚠️ Örnek: {code('/emtia ALTIN')} veya {code('/emtia liste')}",
            parse_mode="HTML")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message,
            f"🏭 {bold('Desteklenen Emtialar')}\n{code(EMTIA_LISTE)}",
            parse_mode="HTML")
        return
    _piyasa_komut(message, girdi, "emtia")


def _piyasa_komut(message, girdi: str, tip: str):
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ {bold(str(bekleme))} saniye bekleyin.",
            parse_mode="HTML")
        return
    _son_istek[user_id] = datetime.now()
    emoji = _TIP_EMOJI.get(tip, "📊")
    bekle_msg = bot.reply_to(message,
        f"⏳ {emoji} {bold(girdi)} verileri çekiliyor...", parse_mode="HTML")
    threading.Thread(target=_piyasa_isle,
        args=(message.chat.id, bekle_msg.message_id, girdi, tip),
        daemon=True).start()


@bot.message_handler(commands=["haber"])
def komut_haber(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            f"⚠️ Örnek: {code('/haber AAPL')} veya {code('/haber ASELS')}",
            parse_mode="HTML")
        return

    girdi   = parcalar[1].upper().strip()
    user_id = message.from_user.id

    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ {bold(str(bekleme))} saniye bekleyin.",
            parse_mode="HTML")
        return
    _son_istek[user_id] = datetime.now()

    # BIST hisseleri için normalize_ticker ile .IS ekle
    girdi_norm = _normalize_ticker(girdi)

    bekle_msg = bot.reply_to(message,
        f"⏳ 📰 {bold(girdi_norm)} haberleri çekiliyor...", parse_mode="HTML")
    threading.Thread(target=_haber_isle,
        args=(message.chat.id, bekle_msg.message_id, girdi_norm),
        daemon=True).start()


@bot.message_handler(commands=["insider"])
def komut_insider(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            f"⚠️ Örnek: {code('/insider AAPL')}", parse_mode="HTML")
        return

    girdi   = parcalar[1].upper().strip()
    user_id = message.from_user.id

    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ {bold(str(bekleme))} saniye bekleyin.",
            parse_mode="HTML")
        return
    _son_istek[user_id] = datetime.now()

    bekle_msg = bot.reply_to(message,
        f"⏳ 🔍 {bold(girdi)} insider verileri çekiliyor...", parse_mode="HTML")
    threading.Thread(target=_insider_isle,
        args=(message.chat.id, bekle_msg.message_id, girdi),
        daemon=True).start()


@bot.message_handler(commands=["trend"])
def komut_trend(message):
    parcalar = message.text.split()
    tip = "kripto" if len(parcalar) > 1 and parcalar[1].lower() in ("kripto","crypto","btc") else "hisse"
    user_id = message.from_user.id

    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ {bold(str(bekleme))} saniye bekleyin.",
            parse_mode="HTML")
        return
    _son_istek[user_id] = datetime.now()

    emoji = "₿" if tip == "kripto" else "📊"
    bekle_msg = bot.reply_to(message,
        f"⏳ {emoji} Trend verileri çekiliyor...", parse_mode="HTML")
    threading.Thread(target=_trend_isle,
        args=(message.chat.id, bekle_msg.message_id, tip),
        daemon=True).start()


@bot.message_handler(commands=["durum"])
def komut_durum(message):
    rapor = durum_raporu()
    bot.reply_to(message, f"<pre>{h(rapor)}</pre>", parse_mode="HTML")


# ─────────────────────────────────────────────
#  THREAD FONKSİYONLARI
# ─────────────────────────────────────────────

def _analiz_isle(chat_id, mesaj_id, hisse_kodu, komut):
    try:
        temel_v = {}
        teknik_v = {}

        if komut in ("analiz","ai"):
            with ThreadPoolExecutor(max_workers=2) as ex:
                ft = ex.submit(temel_analiz_yap, hisse_kodu)
                fk = ex.submit(teknik_analiz_yap, hisse_kodu)
                temel_v  = ft.result()
                teknik_v = fk.result()
        elif komut == "temel":
            temel_v = temel_analiz_yap(hisse_kodu)
        elif komut == "teknik":
            teknik_v = teknik_analiz_yap(hisse_kodu)

        if temel_v and "Hata" in temel_v:
            _gonder(chat_id, mesaj_id, f"❌ {h(temel_v['Hata'])}")
            return
        if teknik_v and "Hata" in teknik_v:
            _gonder(chat_id, mesaj_id, f"❌ {h(teknik_v['Hata'])}")
            return

        # ── TEMEL ANALİZ ──────────────────────────────────────────────────
        if temel_v:
            rapor = (f"📊 {bold(hisse_kodu + ' — TEMEL ANALİZ')}\n"
                     f"<i>{AYRAC}</i>\n")
            for ad, emoji, fn in TEMEL_GRUPLAR:
                blok_html = temel_blok(ad, emoji, temel_v, fn)
                if blok_html:
                    rapor += blok_html + "\n"
            _gonder(chat_id, mesaj_id, rapor.strip(), duzenle=True)

        # ── TEKNİK ANALİZ ─────────────────────────────────────────────────
        if teknik_v:
            MA_KEYS = {"SMA (Basit)","EMA (Üstel)","WMA (Ağırlıklı)"}
            ind_satirlar = []
            for k, v in teknik_v.items():
                if k.startswith("_") or k in MA_KEYS:
                    continue
                v_str = _fmt(v)
                if v_str and v_str not in ("None","nan","0","0.00","N/A",""):
                    ind_satirlar.append((k, v_str))

            tek_rapor = (f"📉 {bold(hisse_kodu + ' — TEKNİK ANALİZ')}\n"
                         f"<i>{AYRAC}</i>\n")
            tek_rapor += blok("TEKNİK İNDİKATÖRLER", "📉", ind_satirlar)
            tek_rapor += ma_blok(teknik_v)

            duzenle = not bool(temel_v)
            _gonder(chat_id, mesaj_id, tek_rapor.strip(), duzenle=duzenle)

        # ── AI YORUMU ─────────────────────────────────────────────────────
        if komut == "ai" and temel_v and teknik_v:
            bot.send_message(chat_id,
                f"🤖 {bold('AI Analist yorumu hazırlanıyor...')}",
                parse_mode="HTML")
            haber_ozeti = ai_icin_haber_ozeti(hisse_kodu)
            if haber_ozeti:
                temel_v["__haberler__"] = haber_ozeti
            yorum = ai_analist_yorumu(hisse_kodu, temel_v, teknik_v)
            baslik = (f"🤖 {bold('AI ANALİST — ' + hisse_kodu)}\n"
                      f"<i>{AYRAC}</i>\n\n")
            tam = baslik + h(yorum)
            for parca in _parcala(tam):
                bot.send_message(chat_id, parca, parse_mode="HTML")

    except Exception as e:
        hata = f"❌ {bold('Sistem Hatası')}\n{code(str(e))}"
        try:
            _gonder(chat_id, mesaj_id, hata, duzenle=True)
        except Exception:
            bot.send_message(chat_id, hata, parse_mode="HTML")


def _piyasa_rapor(goruntu, tip, piyasa, teknik) -> list:
    emoji_tip  = _TIP_EMOJI.get(tip, "📊")
    baslik_tip = _TIP_BASLIK.get(tip, tip.upper())
    mesajlar   = []

    rapor = (f"{emoji_tip} {bold(goruntu + ' — ' + baslik_tip + ' ANALİZİ')}\n"
             f"<i>{AYRAC}</i>\n")
    genel_satirlar = []
    for k in GENEL_ANAHTARLAR.get(tip, []):
        v = piyasa.get(k)
        if v and str(v) not in ("","N/A","0","None"):
            genel_satirlar.append((k, str(v)))
    rapor += blok("Genel Bilgiler", "ℹ️", genel_satirlar)
    mesajlar.append(rapor)

    if teknik and "Hata" not in teknik:
        MA_KEYS = {"SMA (Basit)","EMA (Üstel)","WMA (Ağırlıklı)"}
        ind_satirlar = []
        for k, v in teknik.items():
            if k.startswith("_") or k in MA_KEYS:
                continue
            v_str = _fmt(v)
            if v_str and v_str not in ("None","nan","0","0.00","N/A",""):
                ind_satirlar.append((k, v_str))
        tek_rapor = (f"📉 {bold(goruntu + ' — TEKNİK ANALİZ')}\n"
                     f"<i>{AYRAC}</i>\n")
        tek_rapor += blok("İNDİKATÖRLER", "📉", ind_satirlar)
        tek_rapor += ma_blok(teknik)
        mesajlar.append(tek_rapor)

    return mesajlar


def _piyasa_isle(chat_id, mesaj_id, girdi, tip):
    try:
        if tip == "kripto":
            piyasa, teknik = kripto_analiz(girdi)
        elif tip == "doviz":
            piyasa, teknik = doviz_analiz(girdi)
        else:
            piyasa, teknik = emtia_analiz(girdi)

        if "Hata" in piyasa:
            bot.edit_message_text(f"❌ {h(piyasa['Hata'])}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
            return

        goruntu  = piyasa.get("_goruntu", girdi)
        mesajlar = _piyasa_rapor(goruntu, tip, piyasa, teknik)

        for i, msg in enumerate(mesajlar):
            if i == 0:
                try:
                    bot.edit_message_text(msg, chat_id=chat_id,
                        message_id=mesaj_id, parse_mode="HTML")
                except Exception:
                    bot.send_message(chat_id, msg, parse_mode="HTML")
            else:
                bot.send_message(chat_id, msg, parse_mode="HTML")

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Hata: {h(str(e))}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, f"❌ Hata: {h(str(e))}", parse_mode="HTML")


def _piyasa_ai_isle(chat_id, mesaj_id, girdi, tip):
    try:
        if tip == "kripto":
            piyasa, teknik = kripto_analiz(girdi)
        elif tip == "doviz":
            piyasa, teknik = doviz_analiz(girdi)
        else:
            piyasa, teknik = emtia_analiz(girdi)

        if "Hata" in piyasa:
            bot.edit_message_text(f"❌ {h(piyasa['Hata'])}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
            return

        goruntu  = piyasa.get("_goruntu", girdi)
        mesajlar = _piyasa_rapor(goruntu, tip, piyasa, teknik)

        for i, msg in enumerate(mesajlar):
            if i == 0:
                try:
                    bot.edit_message_text(msg, chat_id=chat_id,
                        message_id=mesaj_id, parse_mode="HTML")
                except Exception:
                    bot.send_message(chat_id, msg, parse_mode="HTML")
            else:
                bot.send_message(chat_id, msg, parse_mode="HTML")

        bot.send_message(chat_id, f"🤖 {bold('AI analiz yorumu hazırlanıyor...')}",
            parse_mode="HTML")
        yorum = ai_piyasa_yorumu(girdi, tip, piyasa, teknik)
        emoji_tip = _TIP_EMOJI.get(tip, "📊")
        baslik = (f"{emoji_tip} {bold('AI ANALİST — ' + goruntu)}\n"
                  f"<i>{AYRAC}</i>\n\n")
        tam = baslik + h(yorum)
        for parca in _parcala(tam):
            bot.send_message(chat_id, parca, parse_mode="HTML")

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Hata: {h(str(e))}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, f"❌ Hata: {h(str(e))}", parse_mode="HTML")


def _haber_isle(chat_id, mesaj_id, sembol):
    try:
        haberler = finnhub_haberler(sembol, gun=14)

        if not haberler:
            fh_notu = ""
            if not os.environ.get("FINNHUB_API_KEY"):
                fh_notu = "\n<i>💡 FINNHUB_API_KEY eklenirse daha fazla kaynak</i>"
            bot.edit_message_text(
                f"📰 {bold(sembol + ' için haber bulunamadı.')}{fh_notu}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
            return

        # kaynaktipi key'i — veri_motoru.py ile uyumlu
        kaynak_tipi = haberler[0].get("kaynaktipi", "")

        rapor = (f"📰 {bold(sembol + ' — SON HABERLER')}\n"
                 f"<i>{AYRAC}</i>\n"
                 f"<i>Kaynak: {h(kaynak_tipi)}</i>\n\n")

        for i, hbr in enumerate(haberler[:8], 1):
            if not hbr.get("baslik"):
                continue
            tarih  = hbr.get("tarih", "")
            baslik_h = hbr.get("baslik", "")
            kaynak = hbr.get("kaynak", "")
            url    = hbr.get("url", "")
            rapor += f"<b>{i}.</b> {h(baslik_h)}\n"
            alt = []
            if tarih and tarih != "-":
                alt.append(f"📅 {tarih}")
            if kaynak:
                alt.append(f"📌 {h(kaynak)}")
            if alt:
                rapor += f"<i>   {'  |  '.join(alt)}</i>\n"
            rapor += "\n"

        _gonder(chat_id, mesaj_id, rapor.strip())

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Hata: {h(str(e))}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
        except Exception:
            pass


def _insider_isle(chat_id, mesaj_id, sembol):
    try:
        islemler = finnhub_insider(sembol)

        if not islemler:
            bist_notu = ""
            if sembol.upper().endswith(".IS"):
                bist_notu = "\n<i>Not: BIST hisseleri için insider verisi mevcut değil.</i>"
            bot.edit_message_text(
                f"🔍 {bold(sembol + ' için insider verisi bulunamadı.')}{bist_notu}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
            return

        # kaynaktipi key'i — veri_motoru.py ile uyumlu
        kaynak_tipi = islemler[0].get("kaynaktipi", "")

        rapor = (f"🔍 {bold(sembol + ' — İNSIDER İŞLEMLER')}\n"
                 f"<i>{AYRAC}</i>\n"
                 f"<i>Kaynak: {h(kaynak_tipi)}</i>\n\n")

        for t in islemler:
            etiket    = "🟢 <b>ALIM</b>" if t["islem"] == "ALIM" else "🔴 <b>SATIM</b>"
            isim      = h(t.get("isim", "")[:28])
            tarih     = h(t.get("tarih", ""))
            adet      = f"{int(t.get('adet', 0)):,}"
            fiyat_ham = t.get("fiyat", 0) or 0
            fiyat     = f"${fiyat_ham:.2f}" if fiyat_ham and fiyat_ham > 0.01 else "—"
            rapor += f"{etiket}  {tarih}\n"
            rapor += f"  👤 {isim}\n"
            rapor += f"  📦 {adet} adet  💵 {fiyat}\n\n"

        _gonder(chat_id, mesaj_id, rapor.strip())

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Hata: {h(str(e))}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
        except Exception:
            pass


def _trend_isle(chat_id, mesaj_id, tip: str = "hisse"):
    try:
        if tip == "kripto":
            cg_trend = coingecko_trending()
            rd_trend = reddit_kripto_trend()

            rapor = (f"₿ {bold('KRİPTO TREND')}\n"
                     f"<i>{AYRAC}</i>\n")

            if cg_trend:
                satirlar = []
                for i, t in enumerate(cg_trend[:8], 1):
                    deg    = t.get("degisim", 0) or 0
                    isaret = "🟢" if deg >= 0 else "🔴"
                    satirlar.append(
                        f"#{i:2}  {t['sembol']:<8}  {isaret} {deg:+.1f}%  {t['isim'][:18]}"
                    )
                rapor += blok("CoinGecko Trend (24s)", "🔥", satirlar)

            if rd_trend:
                satirlar2 = []
                for i, t in enumerate(rd_trend[:8], 1):
                    satirlar2.append(
                        f"#{i:2}  {t['sembol']:<8}  {t['mention']:>5} mention"
                    )
                rapor += "\n" + blok("Reddit Kripto Trend", "💬", satirlar2)

            rapor += f"\n<i>Kaynak: CoinGecko + ApeWisdom</i>"

        else:
            trending = reddit_trend()
            if not trending:
                bot.edit_message_text(
                    "📊 Trend verisi alınamadı.",
                    chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
                return

            satirlar = []
            for i, t in enumerate(trending[:12], 1):
                degisim  = t.get("degisim", 0) or 0
                trend_ok = "📈" if t["mention"] > degisim else "📉"
                satirlar.append(
                    f"#{i:2}  {t['sembol']:<8}  {t['mention']:>5} mention  {trend_ok}"
                )

            rapor = (f"📊 {bold('REDDIT / WSB TREND HİSSELER')}\n"
                     f"<i>{AYRAC}</i>\n")
            rapor += blok("En Çok Konuşulanlar", "🔥", satirlar)
            rapor += f"\n<i>Kaynak: ApeWisdom (Reddit WSB + Stocks)</i>"

        bot.edit_message_text(rapor, chat_id=chat_id,
            message_id=mesaj_id, parse_mode="HTML")

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Hata: {h(str(e))}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
        except Exception:
            pass


# ─────────────────────────────────────────────
#  BAŞLAT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    baslangic_temizligi()
    print(f"[{datetime.now():%H:%M:%S}] 🧹 Cache temizlendi")
    print(f"[{datetime.now():%H:%M:%S}] Bot başlatılıyor...")

    finnhub_key = os.environ.get("FINNHUB_API_KEY","")
    av_key      = os.environ.get("ALPHAVANTAGE_API_KEY","")
    cg_key      = os.environ.get("COINGECKO_API_KEY","")
    print(f"[{datetime.now():%H:%M:%S}] Finnhub:      {'✅' if finnhub_key else '⚠️ KEY YOK'}")
    print(f"[{datetime.now():%H:%M:%S}] AlphaVantage: {'✅' if av_key else '⚠️ KEY YOK'}")
    print(f"[{datetime.now():%H:%M:%S}] CoinGecko:    {'✅' if cg_key else '⚠️ KEY YOK (ücretsiz limit)'}")
    print(f"[{datetime.now():%H:%M:%S}] OpenFIGI:     ✅ (key'siz)")
    print(f"[{datetime.now():%H:%M:%S}] borsapy:      ✅ (key'siz)")
    print(f"[{datetime.now():%H:%M:%S}] SEC EDGAR:    ✅ (key'siz)")

    import time as _time
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30,
                restart_on_change=False, skip_pending=True)
        except Exception as _e:
            print(f"[{datetime.now():%H:%M:%S}] ⚠️ {_e} — 5sn sonra yeniden...")
            _time.sleep(5)
