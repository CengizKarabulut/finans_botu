"""
Finans Botu — aiogram 3.x + asyncio + SQLite
Tüm sync modüller (temel_analiz, teknik_analiz, vb.) run_in_executor ile çağrılır.
✅ DÜZELTİLMİŞ VERSİYON - Tüm kritik hatalar giderildi
"""
import os
import re
import asyncio
import logging
from datetime import datetime
from functools import partial
from logging.handlers import RotatingFileHandler  # ✅ EKLENDİ: Log rotasyonu için
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
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
from db import (
    db_init, favori_ekle, favori_sil, favorileri_getir, kullanici_kaydet,
    uyari_ekle, uyarilari_getir, uyari_sil,
    portfoy_guncelle, portfoy_getir, portfoy_sil
)
from alert_motoru import uyari_kontrol_dongusu
from portfoy_motoru import portfoy_ozeti_hazirla
from tradingview_motoru import tv_grafik_cek
from analist_motoru import ai_tahmin_yap, ai_nlp_sorgu
from aiogram.types import FSInputFile

# ═══════════════════════════════════════════════════════════════
# LOGGING CONFIGURATION — ✅ DÜZELTİLDİ
# ═══════════════════════════════════════════════════════════════
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),  # Docker logs için STDOUT
        RotatingFileHandler(  # ✅ Dosya boyutu kontrolü (10MB, 5 yedek)
            os.path.join(LOG_DIR, "bot.log"),
            maxBytes=10*1024*1024,
            backupCount=5
        )
    ]
)
log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════
# BOT TOKEN VALIDATION — ✅ GÜVENLİK EKLENDİ
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN tanımlı değil. .env dosyasını kontrol edin.")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()

RATE_LIMIT_SANIYE = 15
TELEGRAM_LIMIT    = 4000
_son_istek: dict  = {}

# ═══════════════════════════════════════════════════════════════
# HTML YARDIMCILARI
# ═══════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════
# KUTU ÇİZGİLİ BLOK FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════
AYRAC  = "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄"
_BOX_G = 38

def _gorunen_uzunluk(s: str) -> int:
    import unicodedata
    n = 0
    for c in s:
        try:
            n += 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1
        except Exception:
            n += 1
    return n

def blok(baslik: str, emoji: str, satirlar: list) -> str:
    """Kutu çizgili (╔═══╗) tablo — eski blok() ile aynı arayüz."""
    if not satirlar:
        return ""
    temiz = []
    for s in satirlar:
        if isinstance(s, tuple):
            k, v = s
            v_str = _fmt(v) if not isinstance(v, str) else v
            if not v_str or v_str in ("None","nan","0","0.00","N/A","","—"):
                continue
            temiz.append(("kv", str(k), str(v_str)))
        else:
            if str(s).strip():
                temiz.append(("txt", str(s), ""))
    if not temiz:
        return ""
    G  = _BOX_G
    IC = G - 2
    def _pad(t, g):
        return t + " " * max(0, g - _gorunen_uzunluk(t))
    def _satir_k(ic):
        return "║ " + _pad(ic, IC) + " ║"
    def _kv_k(a, d):
        a_max = min(22, IC - 6)
        d_max = IC - a_max - 1
        ak = a[:a_max-1]+"…" if _gorunen_uzunluk(a) > a_max else a
        dk = d[:d_max-1]+"…" if _gorunen_uzunluk(d) > d_max else d
        return "║ " + _pad(ak, a_max) + " "*max(0, d_max-_gorunen_uzunluk(dk)) + dk + " ║"
    bas = (emoji + "  " + baslik).strip()
    satirlar_html = [
        "╔" + "═"*G + "╗",
        _satir_k(bas),
        "╠" + "═"*G + "╣",
    ]
    for tip, a, b in temiz:
        satirlar_html.append(_kv_k(a, b) if tip == "kv" else _satir_k(a[:IC]))
    satirlar_html.append("╚" + "═"*G + "╝")
    return "\n<pre>" + h("\n".join(satirlar_html)) + "</pre>"

def temel_blok(baslik: str, emoji: str, veriler: dict, filtre) -> str:
    satirlar = []
    for k, v in veriler.items():
        if k.startswith("_") or not filtre(k):
            continue
        v_str = _fmt(v) if not isinstance(v, str) else v
        if not v_str or v_str in ("None","nan","0","0.00","N/A",""):
            continue
        satirlar.append((k, v_str))
    return blok(baslik, emoji, satirlar)

def ma_blok(teknik: dict) -> str:
    satirlar = []
    for tip in ("SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"):
        if tip not in teknik:
            continue
        kisalt  = tip.split()[0]
        parcalar = [p.strip() for p in teknik[tip].split("|")]
        satirlar.append(f"── {kisalt} ──")
        for i in range(0, len(parcalar), 3):
            satirlar.append("  " + "  ".join(parcalar[i:i+3]))
    if not satirlar:
        return ""
    G  = _BOX_G
    IC = G - 2
    bas = "🌊  HAREKETLİ ORTALAMALAR"
    def _pad(t, g):
        return t + " " * max(0, g - _gorunen_uzunluk(t))
    kutu = ["╔" + "═"*G + "╗",
            "║ " + _pad(bas, IC) + " ║",
            "╠" + "═"*G + "╣"]
    for s in satirlar:
        kutu.append("║ " + _pad(s, IC) + " ║")
    kutu.append("╚" + "═"*G + "╝")
    return "\n<pre>" + h("\n".join(kutu)) + "</pre>"

# ═══════════════════════════════════════════════════════════════
# TEMEL ANALİZ GRUPLARI
# ═══════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════
# SEMBOL NORMALIZE
# ═══════════════════════════════════════════════════════════════
_BILINEN_UZANTILAR = {
    ".IS",".L",".PA",".DE",".MI",".AS",".BR",".MC",".SW",
    ".HK",".T",".SS",".SZ",".KS",".KQ",".AX",".TO",".V",
    ".SA",".MX",".NS",".BO",
}

_TICKER_CACHE: dict = {}

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
    "KRDMA","KRDMB","KCAER","ISBIR","SARKY","ENJSA","CLEBI","AKCNS","AKGRT",
    "AKSA","ALBRK","CEMAS","CMBTN","CMENT","CUSAN","DEVA","DNISI","ECZYT",
    "EMKEL","EPLAS","ERBOS","ERSU","FONET","GARFA","GEDIK","GENIL","GENTS",
    "GEREL","GLBMD","GOKNR","GOZDE","GRSEL","GSRAY","GULER","HATEK","HEDEF",
    "HLGYO","HUBVC","HUNER","IHEVA","IHLAS","IMASM","ISFIN","ISGSY","ISMEN",
    "KAYSE","KARTN","KAPLM","KLKIM","KLSER","KNFRT","KONKA","KRONT","KRSTL",
    "LINK","LUKSK","MAKTK","MANAS","MARKA","MEDTR","MEGAP","MERKO","MEYSU",
    "MMCAS","MOBTL","MNDTR","MSGYO","NATEN","NETCD","NTHOL","NUGYO","ODAS",
    "ONCSM","ORGE","ORMA","OSMEN","OTTO","OYYAT","OYLUM","PAHOL","PAMEL",
    "PNLSN","PRDGS","PEKGY","PKART","PLTUR","POLHO","POLTK","PRVAK","QNBFK",
    "RALYH","RNPOL","RYGYO","RODRG","ROYAL","RTALB","RUBNS","SANKO","SANEL",
    "SNICA","SANFM","SAMAT","SAYAS","SDTTR","SEKUR","SELVA","SELEC","SRVGY",
    "SEYKM","SMRTG","SODSN","SOKE","SUMAS","SUNTK","SUWEN","SKTAS","SNPAM",
    "TARKM","TATEN","TEKTU","TKNSA","TMPOL","TRGYO","TRMET","TLMAN","TSPOR",
    "TDGYO","TSGYO","TUKAS","TRCAS","TUREX","TRILC","TUCLK","TMSN","TBORG",
    "TURGG","UCAYM","ULUFA","ULUSE","ULUUN","UMPAS","VAKFA","VAKFN","VKGYO",
    "VAKKO","VANGD","VBTYZ","VERUS","VESBE","YAPRK","YATAS","YYLGD","YAYLA",
    "YGGYO","YEOTK","YGYO","YYAPI","YESIL","YONGA","YKSLN","YUNSA","YBTAS",
    "ZGYO","ZEDUR","ZERGY","ZRGYO","CELHA","OZKGY","OZGYO","UNLU","IDGYO",
    "INTEM","ISDMR","SEKFK","SEGYO","SKYMD","OBAMS","NTHOL","SARKY","PRKAB",
    "KLNMA","TKFEN","TATGD",
}

def _normalize_ticker(ticker: str) -> str:
    import yfinance as yf
    ticker = ticker.upper().strip()
    for uzanti in _BILINEN_UZANTILAR:
        if ticker.endswith(uzanti):
            return ticker
    if ticker in _TICKER_CACHE:
        return _TICKER_CACHE[ticker]
    if ticker in _BIST_HISSELER:
        sonuc = ticker + ".IS"
        _TICKER_CACHE[ticker] = sonuc
        return sonuc
    try:
        if not yf.Ticker(ticker).history(period="5d").empty:
            _TICKER_CACHE[ticker] = ticker
            return ticker
    except Exception as e:
        log.debug(f"yfinance ticker kontrol hatası ({ticker}): {e}")
    ticker_is = ticker + ".IS"
    try:
        if not yf.Ticker(ticker_is).history(period="5d").empty:
            _TICKER_CACHE[ticker] = ticker_is
            return ticker_is
    except Exception as e:
        log.debug(f"yfinance .IS kontrol hatası ({ticker_is}): {e}")
    _TICKER_CACHE[ticker] = ticker
    return ticker

def rate_limit_kontrol(user_id: int) -> int:
    son = _son_istek.get(user_id)
    if son is None:
        return 0
    gecen = (datetime.now() - son).total_seconds()
    return max(0, int(RATE_LIMIT_SANIYE - gecen))

# ═══════════════════════════════════════════════════════════════
# ASYNC YARDIMCI — ✅ DÜZELTİLDİ: get_running_loop()
# ═══════════════════════════════════════════════════════════════
async def _async(fn, *args):
    """Sync bloklayan fonksiyonu thread executor'da çalıştır."""
    loop = asyncio.get_running_loop()  # ✅ get_event_loop() deprecated
    return await loop.run_in_executor(None, fn, *args)

async def _gonder(chat_id: int, mesaj_id: int, metin: str, duzenle: bool = True):
    for i, parca in enumerate(_parcala(metin)):
        try:
            if i == 0 and duzenle:
                await bot.edit_message_text(parca, chat_id=chat_id,
                    message_id=mesaj_id, parse_mode=ParseMode.HTML)
            else:
                await bot.send_message(chat_id, parca, parse_mode=ParseMode.HTML)
        except Exception as e:
            if "message is not modified" not in str(e):
                log.warning(f"Mesaj gönderim hatası: {e}")
                await bot.send_message(chat_id, parca, parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════
# PİYASA RAPOR YARDIMCISI
# ═══════════════════════════════════════════════════════════════
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
            v_str = _fmt(v) if not isinstance(v, str) else v
            if v_str and v_str not in ("None","nan","0","0.00","N/A",""):
                ind_satirlar.append((k, v_str))
        tek_rapor = (f"📉 {bold(goruntu + ' — TEKNİK ANALİZ')}\n"
                     f"<i>{AYRAC}</i>\n")
        tek_rapor += blok("İNDİKATÖRLER", "📉", ind_satirlar)
        tek_rapor += ma_blok(teknik)
        mesajlar.append(tek_rapor)
    return mesajlar

# ═══════════════════════════════════════════════════════════════
# KOMUTLAR
# ═══════════════════════════════════════════════════════════════
@dp.message(CommandStart())
@dp.message(Command("yardim"))
async def komut_yardim(message: Message):
    await kullanici_kaydet(message.from_user.id, message.from_user.username or "")
    metin = (
        f"📈 {bold('Finans Asistanı')}\n"
        f"<i>Türkiye · Dünya · Kripto · Döviz · Emtia</i>\n"
        f"🇹🇷 {bold('BIST Hisseleri')}\n"
        f"{code('/analiz TUPRS')}  Temel + Teknik\n"
        f"{code('/temel  THYAO')}  Yalnızca temel\n"
        f"{code('/teknik ASELS')}  Yalnızca teknik\n"
        f"{code('/ai     ASELS')}  🤖 AI Yorumu\n"
        f"🌍 {bold('Yabancı Hisseler')}\n"
        f"{code('/analiz AAPL  ')}  ABD (direkt sembol)\n"
        f"{code('/analiz SHEL.L')}  Londra  (.L)\n"
        f"{code('/analiz SAP.DE')}  Frankfurt (.DE)\n"
        f"{code('/ai     NVDA  ')}  AI Yorumu\n"
        f"₿ {bold('Kripto')}\n"
        f"{code('/kripto BTC   ')}  Bitcoin (USD)\n"
        f"{code('/kripto ETHTRY')}  Ethereum (TRY)\n"
        f"{code('/ai     BTC   ')}  AI Kripto Yorumu\n"
        f"{code('/kripto liste ')}  Tüm semboller\n"
        f"💱 {bold('Döviz')}\n"
        f"{code('/doviz USDTRY ')}  Dolar/TL\n"
        f"{code('/doviz EURUSD ')}  Euro/Dolar\n"
        f"{code('/doviz liste  ')}  Tüm pariteler\n"
        f"🏭 {bold('Emtia')}\n"
        f"{code('/emtia ALTIN  ')}  Altın vadeli\n"
        f"{code('/emtia PETROL ')}  Ham petrol\n"
        f"{code('/emtia liste  ')}  Tüm emtialar\n"
        f"📰 {bold('Haberler & Insider')}\n"
        f"{code('/haber  AAPL  ')}  Son haberler\n"
        f"{code('/insider AAPL ')}  İçeriden alım/satım\n"
        f"{code('/trend        ')}  Reddit WSB hisse trend\n"
        f"{code('/trend kripto ')}  CoinGecko + Reddit kripto trend\n"
        f"⭐ {bold('Favoriler')}\n"
        f"{code('/favori ekle THYAO')}  Favori ekle\n"
        f"{code('/favori sil  THYAO')}  Favori sil\n"
        f"{code('/favoriler        ')}  Favori listesi\n"
        f"🔧 {bold('Sistem')}\n"
        f"{code('/durum')}  API bağlantı durumu\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"💡 BIST'te {code('.IS')} otomatik eklenir\n"
        f"⏱ Sorgular arası min {bold(str(RATE_LIMIT_SANIYE))} saniye"
    )
    await message.reply(metin)

@dp.message(Command("analiz", "temel", "teknik", "ai"))
async def komut_analiz(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(
            f"⚠️ Sembol belirtin. Örnek: {code('/analiz ASELS')} veya {code('/ai BTC')}")
        return
    girdi   = parcalar[1].upper().strip()
    komut   = message.text.split()[0].lstrip("/").lower()
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        await message.reply(f"⏳ Lütfen {bold(str(bekleme))} saniye bekleyin.")
        return
    _son_istek[user_id] = datetime.now()
    await kullanici_kaydet(user_id, message.from_user.username or "")
    piyasa_tip = None
    if girdi in KRIPTO_MAP or girdi.endswith("-USD") or girdi.endswith("-TRY"):
        piyasa_tip = "kripto"
    elif girdi in DOVIZ_MAP or girdi.endswith("=X"):
        piyasa_tip = "doviz"
    elif girdi in EMTIA_MAP or girdi.endswith("=F"):
        piyasa_tip = "emtia"
    if piyasa_tip:
        if komut == "temel":
            await message.reply(
                f"ℹ️ {bold(girdi)} için temel finansal veri yok.\n"
                f"Bunun yerine: {code(f'/{piyasa_tip} {girdi}')}")
            return
        bekle_msg = await message.reply(f"⏳ {bold(girdi)} analiz ediliyor...")
        if komut == "ai":
            asyncio.get_running_loop().create_task(  # ✅ DÜZELTİLDİ
                _piyasa_ai_isle(message.chat.id, bekle_msg.message_id, girdi, piyasa_tip))
        else:
            asyncio.get_running_loop().create_task(  # ✅ DÜZELTİLDİ
                _piyasa_isle(message.chat.id, bekle_msg.message_id, girdi, piyasa_tip))
        return
    hisse_kodu = await _async(_normalize_ticker, girdi)
    bekle_msg  = await message.reply(f"⏳ {bold(hisse_kodu)} verileri işleniyor...")
    asyncio.get_running_loop().create_task(  # ✅ DÜZELTİLDİ
        _analiz_isle(message.chat.id, bekle_msg.message_id, hisse_kodu, komut))

@dp.message(Command("kripto"))
async def komut_kripto(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: {code('/kripto BTC')} veya {code('/kripto liste')}")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        await message.reply(f"₿ {bold('Desteklenen Kriptolar')}\n{code(KRIPTO_LISTE)}")
        return
    await _piyasa_komut(message, girdi, "kripto")

@dp.message(Command("doviz"))
async def komut_doviz(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: {code('/doviz USDTRY')} veya {code('/doviz liste')}")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        await message.reply(f"💱 {bold('Desteklenen Pariteler')}\n{code(DOVIZ_LISTE)}")
        return
    await _piyasa_komut(message, girdi, "doviz")

@dp.message(Command("emtia"))
async def komut_emtia(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: {code('/emtia ALTIN')} veya {code('/emtia liste')}")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        await message.reply(f"🏭 {bold('Desteklenen Emtialar')}\n{code(EMTIA_LISTE)}")
        return
    await _piyasa_komut(message, girdi, "emtia")

async def _piyasa_komut(message: Message, girdi: str, tip: str):
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        await message.reply(f"⏳ {bold(str(bekleme))} saniye bekleyin.")
        return
    _son_istek[user_id] = datetime.now()
    emoji = _TIP_EMOJI.get(tip, "📊")
    bekle_msg = await message.reply(f"⏳ {emoji} {bold(girdi)} verileri çekiliyor...")
    asyncio.get_running_loop().create_task(  # ✅ DÜZELTİLDİ
        _piyasa_isle(message.chat.id, bekle_msg.message_id, girdi, tip))

@dp.message(Command("haber"))
async def komut_haber(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: {code('/haber AAPL')} veya {code('/haber ASELS')}")
        return
    girdi   = parcalar[1].upper().strip()
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        await message.reply(f"⏳ {bold(str(bekleme))} saniye bekleyin.")
        return
    _son_istek[user_id] = datetime.now()
    girdi_norm = await _async(_normalize_ticker, girdi)
    bekle_msg  = await message.reply(f"⏳ 📰 {bold(girdi_norm)} haberleri çekiliyor...")
    asyncio.get_running_loop().create_task(  # ✅ DÜZELTİLDİ
        _haber_isle(message.chat.id, bekle_msg.message_id, girdi_norm))

@dp.message(Command("insider"))
async def komut_insider(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: {code('/insider AAPL')}")
        return
    girdi   = parcalar[1].upper().strip()
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        await message.reply(f"⏳ {bold(str(bekleme))} saniye bekleyin.")
        return
    _son_istek[user_id] = datetime.now()
    bekle_msg = await message.reply(f"⏳ 🔍 {bold(girdi)} insider verileri çekiliyor...")
    asyncio.get_running_loop().create_task(  # ✅ DÜZELTİLDİ
        _insider_isle(message.chat.id, bekle_msg.message_id, girdi))

@dp.message(Command("trend"))
async def komut_trend(message: Message):
    parcalar = message.text.split()
    tip = "kripto" if len(parcalar) > 1 and parcalar[1].lower() in ("kripto","crypto","btc") else "hisse"
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        await message.reply(f"⏳ {bold(str(bekleme))} saniye bekleyin.")
        return
    _son_istek[user_id] = datetime.now()
    emoji = "₿" if tip == "kripto" else "📊"
    bekle_msg = await message.reply(f"⏳ {emoji} Trend verileri çekiliyor...")
    asyncio.get_running_loop().create_task(  # ✅ DÜZELTİLDİ
        _trend_isle(message.chat.id, bekle_msg.message_id, tip))

@dp.message(Command("favori"))
async def komut_favori(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 3:
        await message.reply(
            f"⚠️ Kullanım:\n"
            f"{code('/favori ekle THYAO')}  — ekle\n"
            f"{code('/favori sil  THYAO')}  — sil")
        return
    islem   = parcalar[1].lower()
    sembol  = parcalar[2].upper().strip()
    user_id = message.from_user.id
    await kullanici_kaydet(user_id, message.from_user.username or "")
    if islem == "ekle":
        await favori_ekle(user_id, sembol)
        await message.reply(f"⭐ {bold(sembol)} favorilere eklendi.")
    elif islem == "sil":
        await favori_sil(user_id, sembol)
        await message.reply(f"🗑 {bold(sembol)} favorilerden silindi.")
    else:
        await message.reply(f"⚠️ Geçersiz işlem. {code('ekle')} veya {code('sil')} kullan.")

@dp.message(Command("favoriler"))
async def komut_favoriler(message: Message):
    user_id = message.from_user.id
    await kullanici_kaydet(user_id, message.from_user.username or "")
    liste = await favorileri_getir(user_id)
    if not liste:
        await message.reply(
            f"⭐ Henüz favori hisse eklemediniz.\n"
            f"Eklemek için: {code('/favori ekle THYAO')}")
        return
    satirlar = [f"  {i+1:2}. {s}" for i, s in enumerate(liste)]
    await message.reply(
        f"⭐ {bold('Favori Hisseleriniz')}\n"
        f"<pre>{h(chr(10).join(satirlar))}</pre>\n"
        f"Analiz için: {code('/analiz THYAO')}")

@dp.message(Command("durum"))
async def komut_durum(message: Message):
    rapor = await _async(durum_raporu)
    await message.reply(f"<pre>{h(rapor)}</pre>")

# ═══════════════════════════════════════════════════════════════
# ASYNC TASK FONKSİYONLARI — ✅ HATA YÖNETİMİ İYİLEŞTİRİLDİ
# ═══════════════════════════════════════════════════════════════
async def _analiz_isle(chat_id: int, mesaj_id: int, hisse_kodu: str, komut: str):
    try:
        temel_v  = {}
        teknik_v = {}
        if komut in ("analiz","ai"):
            temel_v, teknik_v = await asyncio.gather(
                _async(temel_analiz_yap, hisse_kodu),
                _async(teknik_analiz_yap, hisse_kodu),
            )
        elif komut == "temel":
            temel_v = await _async(temel_analiz_yap, hisse_kodu)
        elif komut == "teknik":
            teknik_v = await _async(teknik_analiz_yap, hisse_kodu)
        if temel_v and "Hata" in temel_v:
            await _gonder(chat_id, mesaj_id, f"❌ {h(temel_v['Hata'])}")
            return
        if teknik_v and "Hata" in teknik_v:
            await _gonder(chat_id, mesaj_id, f"❌ {h(teknik_v['Hata'])}")
            return
        # ── TEMEL ANALİZ ──────────────────────────────────────────────
        if temel_v:
            rapor = (f"📊 {bold(hisse_kodu + ' — TEMEL ANALİZ')}\n"
                     f"<i>{AYRAC}</i>\n")
            for ad, emoji, fn in TEMEL_GRUPLAR:
                blok_html = temel_blok(ad, emoji, temel_v, fn)
                if blok_html:
                    rapor += blok_html + "\n"
            await _gonder(chat_id, mesaj_id, rapor.strip(), duzenle=True)
        # ── TEKNİK ANALİZ ─────────────────────────────────────────────
        if teknik_v:
            MA_KEYS = {"SMA (Basit)","EMA (Üstel)","WMA (Ağırlıklı)"}
            ind_satirlar = []
            for k, v in teknik_v.items():
                if k.startswith("_") or k in MA_KEYS:
                    continue
                v_str = _fmt(v) if not isinstance(v, str) else v
                if v_str and v_str not in ("None","nan","0","0.00","N/A",""):
                    ind_satirlar.append((k, v_str))
            tek_rapor = (f"📉 {bold(hisse_kodu + ' — TEKNİK ANALİZ')}\n"
                         f"<i>{AYRAC}</i>\n")
            tek_rapor += blok("TEKNİK İNDİKATÖRLER", "📉", ind_satirlar)
            tek_rapor += ma_blok(teknik_v)
            duzenle = not bool(temel_v)
            await _gonder(chat_id, mesaj_id, tek_rapor.strip(), duzenle=duzenle)
        # ── AI YORUMU ─────────────────────────────────────────────────
        if komut == "ai" and temel_v and teknik_v:
            await bot.send_message(chat_id, f"🤖 {bold('AI Analist yorumu hazırlanıyor...')}")
            haber_ozeti = await _async(ai_icin_haber_ozeti, hisse_kodu)
            if haber_ozeti:
                temel_v["__haberler__"] = haber_ozeti
            yorum = await _async(ai_analist_yorumu, hisse_kodu, temel_v, teknik_v)
            baslik = (f"🤖 {bold('AI ANALİST — ' + hisse_kodu)}\n"
                      f"<i>{AYRAC}</i>\n")
            tam = baslik + h(yorum)
            for parca in _parcala(tam):
                await bot.send_message(chat_id, parca)
    except Exception as e:
        log.exception("_analiz_isle hata")  # ✅ exc_info otomatik
        hata = f"❌ {bold('Sistem Hatası')}\n{code(str(e))}"
        try:
            await _gonder(chat_id, mesaj_id, hata)
        except Exception:
            await bot.send_message(chat_id, hata)

async def _piyasa_isle(chat_id: int, mesaj_id: int, girdi: str, tip: str):
    try:
        if tip == "kripto":
            piyasa, teknik = await _async(kripto_analiz, girdi)
        elif tip == "doviz":
            piyasa, teknik = await _async(doviz_analiz, girdi)
        else:
            piyasa, teknik = await _async(emtia_analiz, girdi)
        if "Hata" in piyasa:
            await _gonder(chat_id, mesaj_id, f"❌ {h(piyasa['Hata'])}")
            return
        goruntu  = piyasa.get("_goruntu", girdi)
        mesajlar = _piyasa_rapor(goruntu, tip, piyasa, teknik)
        for i, msg in enumerate(mesajlar):
            if i == 0:
                await _gonder(chat_id, mesaj_id, msg, duzenle=True)
            else:
                await bot.send_message(chat_id, msg)
    except Exception as e:
        log.exception("_piyasa_isle hata")  # ✅ exc_info otomatik
        try:
            await _gonder(chat_id, mesaj_id, f"❌ Hata: {h(str(e))}")
        except Exception:
            await bot.send_message(chat_id, f"❌ Hata: {h(str(e))}")

async def _piyasa_ai_isle(chat_id: int, mesaj_id: int, girdi: str, tip: str):
    try:
        if tip == "kripto":
            piyasa, teknik = await _async(kripto_analiz, girdi)
        elif tip == "doviz":
            piyasa, teknik = await _async(doviz_analiz, girdi)
        else:
            piyasa, teknik = await _async(emtia_analiz, girdi)
        if "Hata" in piyasa:
            await _gonder(chat_id, mesaj_id, f"❌ {h(piyasa['Hata'])}")
            return
        goruntu  = piyasa.get("_goruntu", girdi)
        mesajlar = _piyasa_rapor(goruntu, tip, piyasa, teknik)
        for i, msg in enumerate(mesajlar):
            if i == 0:
                await _gonder(chat_id, mesaj_id, msg, duzenle=True)
            else:
                await bot.send_message(chat_id, msg)
        await bot.send_message(chat_id, f"🤖 {bold('AI analiz yorumu hazırlanıyor...')}")
        yorum = await _async(ai_piyasa_yorumu, girdi, tip, piyasa, teknik)
        emoji_tip = _TIP_EMOJI.get(tip, "📊")
        baslik = (f"{emoji_tip} {bold('AI ANALİST — ' + goruntu)}\n"
                  f"<i>{AYRAC}</i>\n")
        tam = baslik + h(yorum)
        for parca in _parcala(tam):
            await bot.send_message(chat_id, parca)
    except Exception as e:
        log.exception("_piyasa_ai_isle hata")  # ✅ exc_info otomatik
        try:
            await _gonder(chat_id, mesaj_id, f"❌ Hata: {h(str(e))}")
        except Exception:
            await bot.send_message(chat_id, f"❌ Hata: {h(str(e))}")

async def _haber_isle(chat_id: int, mesaj_id: int, sembol: str):
    try:
        haberler = await _async(finnhub_haberler, sembol, 14)
        if not haberler:
            fh_notu = ""
            if not os.environ.get("FINNHUB_API_KEY"):
                fh_notu = "\n<i>💡 FINNHUB_API_KEY eklenirse daha fazla kaynak</i>"
            await _gonder(chat_id, mesaj_id,
                f"📰 {bold(sembol + ' için haber bulunamadı.')}{fh_notu}")
            return
        kaynak_tipi = haberler[0].get("kaynaktipi", "")
        rapor = (f"📰 {bold(sembol + ' — SON HABERLER')}\n"
                 f"<i>{AYRAC}</i>\n"
                 f"<i>Kaynak: {h(kaynak_tipi)}</i>\n")
        for i, hbr in enumerate(haberler[:8], 1):
            if not hbr.get("baslik"):
                continue
            tarih    = hbr.get("tarih", "")
            baslik_h = hbr.get("baslik", "")
            kaynak   = hbr.get("kaynak", "")
            rapor   += f"<b>{i}.</b> {h(baslik_h)}\n"
            alt = []
            if tarih and tarih != "-":
                alt.append(f"📅 {tarih}")
            if kaynak:
                alt.append(f"📌 {h(kaynak)}")
            if alt:
                rapor += f"<i>   {'  |  '.join(alt)}</i>\n"
            rapor += "\n"
        await _gonder(chat_id, mesaj_id, rapor.strip())
    except Exception as e:
        log.exception("_haber_isle hata")  # ✅ exc_info otomatik
        try:
            await _gonder(chat_id, mesaj_id, f"❌ Hata: {h(str(e))}")
        except Exception:
            pass

async def _insider_isle(chat_id: int, mesaj_id: int, sembol: str):
    try:
        islemler = await _async(finnhub_insider, sembol)
        if not islemler:
            bist_notu = ""
            if sembol.upper().endswith(".IS"):
                bist_notu = "\n<i>Not: BIST hisseleri için insider verisi mevcut değil.</i>"
            await _gonder(chat_id, mesaj_id,
                f"🔍 {bold(sembol + ' için insider verisi bulunamadı.')}{bist_notu}")
            return
        kaynak_tipi = islemler[0].get("kaynaktipi", "")
        rapor = (f"🔍 {bold(sembol + ' — İNSIDER İŞLEMLER')}\n"
                 f"<i>{AYRAC}</i>\n"
                 f"<i>Kaynak: {h(kaynak_tipi)}</i>\n")
        for t in islemler:
            etiket    = "🟢 <b>ALIM</b>" if t["islem"] == "ALIM" else "🔴 <b>SATIM</b>"
            isim      = h(t.get("isim", "")[:28])
            tarih     = h(t.get("tarih", ""))
            adet      = f"{int(t.get('adet', 0)):,}"
            fiyat_ham = t.get("fiyat", 0) or 0
            fiyat     = f"${fiyat_ham:.2f}" if fiyat_ham and fiyat_ham > 0.01 else "—"
            rapor    += f"{etiket}  {tarih}\n"
            rapor    += f"  👤 {isim}\n"
            rapor    += f"  📦 {adet} adet  💵 {fiyat}\n"
        await _gonder(chat_id, mesaj_id, rapor.strip())
    except Exception as e:
        log.exception("_insider_isle hata")  # ✅ exc_info otomatik
        try:
            await _gonder(chat_id, mesaj_id, f"❌ Hata: {h(str(e))}")
        except Exception:
            pass

async def _trend_isle(chat_id: int, mesaj_id: int, tip: str = "hisse"):
    try:
        if tip == "kripto":
            cg_trend, rd_trend = await asyncio.gather(
                _async(coingecko_trending),
                _async(reddit_kripto_trend),
            )
            rapor = (f"₿ {bold('KRİPTO TREND')}\n"
                     f"<i>{AYRAC}</i>\n")
            if cg_trend:
                satirlar = []
                for i, t in enumerate(cg_trend[:8], 1):
                    deg    = t.get("degisim", 0) or 0
                    isaret = "🟢" if deg >= 0 else "🔴"
                    satirlar.append(f"#{i:2}  {t['sembol']:<8}  {isaret} {deg:+.1f}%  {t['isim'][:18]}")
                rapor += blok("CoinGecko Trend (24s)", "🔥", satirlar)
            if rd_trend:
                satirlar2 = []
                for i, t in enumerate(rd_trend[:8], 1):
                    satirlar2.append(f"#{i:2}  {t['sembol']:<8}  {t['mention']:>5} mention")
                rapor += "\n" + blok("Reddit Kripto Trend", "💬", satirlar2)
            rapor += f"\n<i>Kaynak: CoinGecko + ApeWisdom</i>"
        else:
            trending = await _async(reddit_trend)
            if not trending:
                await _gonder(chat_id, mesaj_id, "📊 Trend verisi alınamadı.")
                return
            satirlar = []
            for i, t in enumerate(trending[:12], 1):
                degisim  = t.get("degisim", 0) or 0
                trend_ok = "📈" if t["mention"] > degisim else "📉"
                satirlar.append(f"#{i:2}  {t['sembol']:<8}  {t['mention']:>5} mention  {trend_ok}")
            rapor = (f"📊 {bold('REDDIT / WSB TREND HİSSELER')}\n"
                     f"<i>{AYRAC}</i>\n")
            rapor += blok("En Çok Konuşulanlar", "🔥", satirlar)
            rapor += f"\n<i>Kaynak: ApeWisdom (Reddit WSB + Stocks)</i>"
        await _gonder(chat_id, mesaj_id, rapor)
    except Exception as e:
        log.exception("_trend_isle hata")  # ✅ exc_info otomatik
        try:
            await _gonder(chat_id, mesaj_id, f"❌ Hata: {h(str(e))}")
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════
# YENİ ÖZELLİK HANDLERLARI
# ═══════════════════════════════════════════════════════════════
@dp.message(Command("uyari"))
async def cmd_uyari(message: Message):
    """Kullanım: /uyari SEMBOL TIP HEDEF (Örn: /uyari THYAO.IS fiyat_ust 300)"""
    try:
        args = message.text.split()
        if len(args) < 4:
            await message.answer("❌ Eksik bilgi. Kullanım: <code>/uyari SEMBOL TIP HEDEF</code>\n"
                                "Tipler: fiyat_ust, fiyat_alt, rsi_ust, rsi_alt")
            return
        sembol, tip, hedef = args[1].upper(), args[2].lower(), float(args[3])
        await uyari_ekle(message.from_user.id, sembol, tip, hedef)
        await message.answer(f"✅ {sembol} için {tip} uyarısı {hedef} seviyesine kuruldu.")
    except Exception as e:
        log.exception("cmd_uyari hata")
        await message.answer(f"❌ Hata: {e}")

@dp.message(Command("portfoy"))
async def cmd_portfoy(message: Message):
    """Portföy özetini gösterir."""
    await message.answer("⌛ Portföyünüz hesaplanıyor...")
    ozet = await portfoy_ozeti_hazirla(message.from_user.id)
    await message.answer(ozet)

@dp.message(Command("portfoy_ekle"))
async def cmd_portfoy_ekle(message: Message):
    """Kullanım: /portfoy_ekle SEMBOL MIKTAR MALIYET"""
    try:
        args = message.text.split()
        if len(args) < 4:
            await message.answer("❌ Kullanım: <code>/portfoy_ekle SEMBOL MIKTAR MALIYET</code>")
            return
        sembol, miktar, maliyet = args[1].upper(), float(args[2]), float(args[3])
        await portfoy_guncelle(message.from_user.id, sembol, miktar, maliyet)
        await message.answer(f"✅ {sembol} portföyünüze eklendi/güncellendi.")
    except Exception as e:
        log.exception("cmd_portfoy_ekle hata")
        await message.answer(f"❌ Hata: {e}")

@dp.message(Command("grafik"))
async def cmd_grafik(message: Message):
    """TradingView grafiği gönderir. Kullanım: /grafik SEMBOL"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Kullanım: <code>/grafik SEMBOL</code>")
        return
    sembol = args[1].upper()
    await message.answer(f"📊 {sembol} grafiği hazırlanıyor, lütfen bekleyin...")
    path = f"logs/chart_{message.from_user.id}.png"
    success = await tv_grafik_cek(sembol, path)
    if success:
        photo = FSInputFile(path)
        await message.answer_photo(photo, caption=f"📈 {sembol} TradingView Grafiği")
    else:
        await message.answer("❌ Grafik çekilemedi. Lütfen sembolü kontrol edin.")

@dp.message(Command("tahmin"))
async def cmd_tahmin(message: Message):
    """AI tahmini yapar. Kullanım: /tahmin SEMBOL"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Kullanım: <code>/tahmin SEMBOL</code>")
        return
    sembol = args[1].upper()
    await message.answer(f"🤖 {sembol} için AI tahmini hazırlanıyor...")
    teknik = await _async(teknik_analiz_yap, sembol)
    tahmin = await _async(ai_tahmin_yap, sembol, teknik)
    await message.answer(f"🔮 <b>{sembol} AI Tahmini</b>\n{tahmin}")

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_nlp(message: Message):
    """Komut olmayan mesajları AI asistanı olarak yanıtlar."""
    await kullanici_kaydet(message.from_user.id, message.from_user.username)
    yanit = await _async(ai_nlp_sorgu, message.text)
    await message.answer(yanit)

# ═══════════════════════════════════════════════════════════════
# BAŞLAT — ✅ EVENT LOOP DÜZELTİLDİ
# ═══════════════════════════════════════════════════════════════
async def main():
    await db_init()
    baslangic_temizligi()
    log.info("Bot başlatılıyor...")
    
    # ✅ DÜZELTİLDİ: Event loop başladıktan sonra task oluştur
    loop = asyncio.get_running_loop()
    loop.create_task(uyari_kontrol_dongusu(bot))
    
    log.info(f"Finnhub:      {'✅' if os.environ.get('FINNHUB_API_KEY') else '⚠️ KEY YOK'}")
    log.info(f"AlphaVantage: {'✅' if os.environ.get('ALPHAVANTAGE_API_KEY') else '⚠️ KEY YOK'}")
    log.info(f"Gemini:       {'✅' if os.environ.get('GEMINI_API_KEY') else '⚠️ KEY YOK'}")
    log.info(f"Anthropic:    {'✅' if os.environ.get('ANTHROPIC_API_KEY') else '⚠️ KEY YOK'}")
    
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
