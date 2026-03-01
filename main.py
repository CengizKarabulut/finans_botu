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

# ─────────────────────────────────────────────
#  YAPILANDIRMA
# ─────────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN ortam değişkeni tanımlı değil.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

_son_istek: dict = {}
RATE_LIMIT_SANIYE = 15
TELEGRAM_LIMIT    = 4096

# ─────────────────────────────────────────────
#  TEMEL ANALİZ BÖLÜM GRUPLARI
# ─────────────────────────────────────────────

TEMEL_GRUPLAR = {
    ("Piyasa Verileri", "💹"): lambda k: k in (
        "Fiyat", "Piyasa Değeri", "F/K (Günlük)", "PD/DD (Günlük)", "FD/FAVÖK (Günlük)",
        "BETA (yFinance)", "BETA (Manuel 1Y)", "BETA (Manuel 2Y)",
        "PEG Oranı (Günlük)", "Fiili Dolaşım (%)", "Yabancı Oranı (%)",
        "⚠️ Veri Tutarsızlığı", "✅ Veri Doğrulaması"
    ),
    ("Analist & Ortaklık", "🎯"): lambda k: k in (
        "Analist Hedef — Ort (TL)", "Analist Hedef — Med (TL)",
        "Analist Hedef — Min (TL)", "Analist Hedef — Maks (TL)",
        "Analist Sayısı", "Ana Ortaklar"
    ),
    ("Sektörel Karşılaştırma", "📊"): lambda k: "Sektör" in k and "Karşılaştırma" not in k,
    ("Değerleme", "🏷"): lambda k: k in (
        "F/K (Hesaplanan)", "PD/DD (Hesaplanan)", "F/S (Fiyat/Satış)",
        "EV/EBITDA (Hesaplanan)", "EV/EBIT", "EV/Sales", "PEG Oranı (Hesaplanan)"
    ),
    ("Karlılık — Yıllık", "📈"): lambda k: "Yıllık" in k and any(
        x in k for x in ["Marjı", "Karlılık", "ROE", "ROA", "ROIC"]
    ) or k == "ROIC (%)",
    ("Karlılık — Çeyreklik", "📊"): lambda k: "Çeyreklik" in k and any(
        x in k for x in ["Marjı", "Karlılık"]
    ),
    ("Büyüme", "🚀"): lambda k: "Büyüme" in k or k == "EPS Büyümesi — Yıllık (%)",
    ("Likidite", "💧"): lambda k: k in (
        "Cari Oran", "Likidite Oranı (Hızlı)", "Nakit Oranı"
    ),
    ("Borç / Kaldıraç", "🏦"): lambda k: k in (
        "Borç / Özsermaye (D/E)", "Finansal Borç / Özsermaye (%)",
        "Net Borç / FAVÖK", "Faiz Karşılama Oranı", "Finansal Borç / Varlık (%)"
    ),
    ("Faaliyet Etkinliği", "⚙️"): lambda k: k in (
        "Varlık Devir Hızı", "Stok Devir Hızı", "Alacak Devir Hızı",
        "Stok Günü (DSI)", "Alacak Günü (DSO)"
    ),
    ("Nakit Akışı", "💵"): lambda k: k in (
        "FCF (Serbest Nakit Akışı)", "FCF Getirisi (%)", "FCF / Net Kar",
        "Temettü Verimi (%)", "Temettü Ödeme Oranı (%)"
    ),
}

# ─────────────────────────────────────────────
#  HTML FORMAT FONKSİYONLARI
# ─────────────────────────────────────────────

def _html(text: str) -> str:
    """HTML özel karakterleri escape et."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_deger(v) -> str:
    """Sayısal değerleri okunabilir formata çevirir."""
    if isinstance(v, float):
        if abs(v) >= 1_000_000_000_000:
            return f"{v/1_000_000_000_000:.2f}T"
        elif abs(v) >= 1_000_000_000:
            return f"{v/1_000_000_000:.2f}B"
        elif abs(v) >= 1_000_000:
            return f"{v/1_000_000:.2f}M"
        else:
            return f"{v:,.2f}"
    elif isinstance(v, int):
        if abs(v) > 1_000_000_000_000:
            return f"{v/1_000_000_000_000:.2f}T"
        elif abs(v) > 1_000_000_000:
            return f"{v/1_000_000_000:.2f}B"
        elif abs(v) > 1_000_000:
            return f"{v/1_000_000:.2f}M"
    return str(v)


def bolum_olustur_html(baslik: str, emoji: str, veriler: dict, filtre_fn=None) -> str:
    """
    HTML formatında bölüm bloğu oluşturur.
    Görünüm: başlık bold, satırlar monospace tablo.
    """
    satirlar = []
    for k, v in veriler.items():
        if k.startswith("_"):
            continue
        if filtre_fn and not filtre_fn(k):
            continue
        v_str = _fmt_deger(v)
        if not v_str or v_str in ("None", "nan", "0", "0.00", "N/A"):
            continue
        satirlar.append(f"  {_html(k):<36}: {_html(v_str)}")

    if not satirlar:
        return ""

    icerik = "\n".join(satirlar)
    return f"<b>{emoji} {_html(baslik)}</b>\n<pre>{icerik}</pre>"


def bolum_olustur_html_liste(baslik: str, emoji: str, satirlar_liste: list) -> str:
    """Hazır satır listesinden HTML bölümü oluşturur."""
    if not satirlar_liste:
        return ""
    icerik = "\n".join(f"  {_html(s)}" for s in satirlar_liste)
    return f"<b>{emoji} {_html(baslik)}</b>\n<pre>{icerik}</pre>"


def _parcala_html(metin: str, limit: int = 4000) -> list:
    """HTML mesajı Telegram limitini aşmayacak şekilde böler."""
    if len(metin) <= limit:
        return [metin]

    parcalar = []
    while len(metin) > limit:
        # </pre> tag sınırında kes
        kesim = metin.rfind("</pre>", 0, limit)
        if kesim != -1:
            kesim += len("</pre>")
        else:
            kesim = metin.rfind("\n", 0, limit)
            if kesim == -1:
                kesim = limit
        parcalar.append(metin[:kesim])
        metin = metin[kesim:].lstrip("\n")

    if metin.strip():
        parcalar.append(metin)
    return parcalar


def _gonder_html(chat_id: int, mesaj_id: int, metin: str, duzenle: bool = True):
    """HTML parse_mode ile mesaj gönder/düzenle."""
    for i, parca in enumerate(_parcala_html(metin)):
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
#  SEMBOL NORMALIZE
# ─────────────────────────────────────────────

_BILINEN_UZANTILAR = {
    ".IS", ".L", ".PA", ".DE", ".MI", ".AS", ".BR", ".MC", ".SW",
    ".HK", ".T", ".SS", ".SZ", ".KS", ".KQ", ".AX", ".TO", ".V",
    ".SA", ".MX", ".NS", ".BO",
}
_TICKER_CACHE: dict = {}


def _normalize_ticker(ticker: str) -> str:
    import yfinance as yf
    ticker = ticker.upper().strip()
    for uzanti in _BILINEN_UZANTILAR:
        if ticker.endswith(uzanti):
            return ticker
    if ticker in _TICKER_CACHE:
        return _TICKER_CACHE[ticker]
    try:
        info = yf.Ticker(ticker).fast_info
        fiyat = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        if fiyat and float(fiyat) > 0:
            _TICKER_CACHE[ticker] = ticker
            return ticker
    except Exception:
        pass
    ticker_is = ticker + ".IS"
    try:
        info = yf.Ticker(ticker_is).fast_info
        fiyat = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        if fiyat and float(fiyat) > 0:
            _TICKER_CACHE[ticker] = ticker_is
            return ticker_is
    except Exception:
        pass
    _TICKER_CACHE[ticker] = ticker_is
    return ticker_is


# ─────────────────────────────────────────────
#  RATE LIMIT
# ─────────────────────────────────────────────

def rate_limit_kontrol(user_id: int) -> int:
    son = _son_istek.get(user_id)
    if son is None:
        return 0
    gecen = (datetime.now() - son).total_seconds()
    return max(0, int(RATE_LIMIT_SANIYE - gecen))


# ─────────────────────────────────────────────
#  KOMUT: /start ve /yardim
# ─────────────────────────────────────────────

@bot.message_handler(commands=["start", "yardim"])
def komut_yardim(message):
    metin = (
        "📈 <b>Finans Asistanı</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🇹🇷 <b>BIST Hisseleri</b>\n"
        "<code>/analiz TUPRS</code>  — Temel + Teknik\n"
        "<code>/temel  THYAO</code>  — Yalnızca temel\n"
        "<code>/teknik ASELS</code>  — Yalnızca teknik\n"
        "<code>/ai     ASELS</code>  — 🤖 AI Yorumu\n\n"

        "🌍 <b>Yabancı Hisseler</b>\n"
        "<code>/analiz AAPL  </code>  — ABD (doğrudan sembol)\n"
        "<code>/analiz SHEL.L</code>  — Londra (.L)\n"
        "<code>/analiz SAP.DE</code>  — Frankfurt (.DE)\n"
        "<code>/ai     NVDA  </code>  — AI Yorumu\n\n"

        "₿ <b>Kripto</b>\n"
        "<code>/kripto BTC   </code>  — Bitcoin (USD)\n"
        "<code>/kripto ETHTRY</code>  — Ethereum (TRY)\n"
        "<code>/ai     BTC   </code>  — AI Kripto Yorumu\n"
        "<code>/kripto liste </code>  — Tüm semboller\n\n"

        "💱 <b>Döviz</b>\n"
        "<code>/doviz USDTRY </code>  — Dolar/TL\n"
        "<code>/doviz EURUSD </code>  — Euro/Dolar\n"
        "<code>/ai    USDTRY </code>  — AI Döviz Yorumu\n"
        "<code>/doviz liste  </code>  — Tüm pariteler\n\n"

        "🏭 <b>Emtia</b>\n"
        "<code>/emtia ALTIN  </code>  — Altın vadeli\n"
        "<code>/emtia PETROL </code>  — Ham petrol\n"
        "<code>/ai    ALTIN  </code>  — AI Emtia Yorumu\n"
        "<code>/emtia liste  </code>  — Tüm emtialar\n\n"

        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 BIST'te <code>.IS</code> uzantısı opsiyonel — otomatik eklenir\n"
        f"⏱ Sorgular arası en az <b>{RATE_LIMIT_SANIYE} saniye</b> bekleme uygulanır"
    )
    bot.reply_to(message, metin, parse_mode="HTML")


# ─────────────────────────────────────────────
#  KOMUT: /analiz /temel /teknik /ai
# ─────────────────────────────────────────────

@bot.message_handler(commands=["analiz", "temel", "teknik", "ai"])
def komut_analiz(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            "⚠️ Sembol belirtin.\nÖrnek: <code>/analiz ASELS</code> veya <code>/ai BTC</code>",
            parse_mode="HTML")
        return

    girdi   = parcalar[1].upper().strip()
    komut   = parcalar[0].lstrip("/").lower()
    user_id = message.from_user.id

    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message,
            f"⏳ Lütfen <b>{bekleme}</b> saniye bekleyin.",
            parse_mode="HTML")
        return
    _son_istek[user_id] = datetime.now()

    # Piyasa tipi algıla
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
                f"ℹ️ <b>{_html(girdi)}</b> için temel finansal veri yok.\n"
                f"Bunun yerine: <code>/{piyasa_tip} {girdi}</code>",
                parse_mode="HTML")
            return
        bekle_msg = bot.reply_to(message,
            f"⏳ <b>{_html(girdi)}</b> analiz ediliyor...", parse_mode="HTML")
        hedef = _piyasa_ai_isle if komut == "ai" else _piyasa_isle
        threading.Thread(target=hedef,
            args=(message.chat.id, bekle_msg.message_id, girdi, piyasa_tip),
            daemon=True).start()
        return

    # BIST / yabancı hisse
    hisse_kodu = _normalize_ticker(girdi)
    bekle_msg = bot.reply_to(message,
        f"⏳ <b>{_html(hisse_kodu)}</b> verileri işleniyor...", parse_mode="HTML")
    threading.Thread(target=_analiz_isle,
        args=(message.chat.id, bekle_msg.message_id, hisse_kodu, komut),
        daemon=True).start()


# ─────────────────────────────────────────────
#  KOMUTLAR: /kripto /doviz /emtia
# ─────────────────────────────────────────────

@bot.message_handler(commands=["kripto"])
def komut_kripto(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            "⚠️ Örnek: <code>/kripto BTC</code> veya <code>/kripto liste</code>",
            parse_mode="HTML")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message,
            f"₿ <b>Desteklenen Kriptolar</b>\n<code>{_html(KRIPTO_LISTE)}</code>",
            parse_mode="HTML")
        return
    _piyasa_komut_isle(message, girdi, "kripto")


@bot.message_handler(commands=["doviz"])
def komut_doviz(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            "⚠️ Örnek: <code>/doviz USDTRY</code> veya <code>/doviz liste</code>",
            parse_mode="HTML")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message,
            f"💱 <b>Desteklenen Pariteler</b>\n<code>{_html(DOVIZ_LISTE)}</code>",
            parse_mode="HTML")
        return
    _piyasa_komut_isle(message, girdi, "doviz")


@bot.message_handler(commands=["emtia"])
def komut_emtia(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message,
            "⚠️ Örnek: <code>/emtia ALTIN</code> veya <code>/emtia liste</code>",
            parse_mode="HTML")
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message,
            f"🏭 <b>Desteklenen Emtialar</b>\n<code>{_html(EMTIA_LISTE)}</code>",
            parse_mode="HTML")
        return
    _piyasa_komut_isle(message, girdi, "emtia")


def _piyasa_komut_isle(message, girdi: str, tip: str):
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message,
            f"⏳ Lütfen <b>{bekleme}</b> saniye bekleyin.", parse_mode="HTML")
        return
    _son_istek[user_id] = datetime.now()
    emoji = _TIP_EMOJI.get(tip, "📊")
    bekle_msg = bot.reply_to(message,
        f"⏳ {emoji} <b>{_html(girdi)}</b> verileri çekiliyor...", parse_mode="HTML")
    threading.Thread(target=_piyasa_isle,
        args=(message.chat.id, bekle_msg.message_id, girdi, tip),
        daemon=True).start()


# ─────────────────────────────────────────────
#  PİYASA THREAD — kripto/döviz/emtia
# ─────────────────────────────────────────────

_TIP_EMOJI  = {"kripto": "₿", "doviz": "💱", "emtia": "🏭"}
_TIP_BASLIK = {"kripto": "KRİPTO ANALİZİ", "doviz": "DÖVİZ ANALİZİ", "emtia": "EMTİA ANALİZİ"}

GENEL_ANAHTARLAR = {
    "kripto": ["Isim", "Para Birimi", "Fiyat", "Degisim (%)",
               "Piyasa Degeri", "Hacim (24s)", "Dolasim Arzi", "Maks Arz"],
    "doviz":  ["Parite", "Aciklama", "Fiyat", "Degisim (%)",
               "Getiri (1 Hafta)", "Getiri (1 Ay)", "Getiri (3 Ay)", "Getiri (1 Yil)"],
    "emtia":  ["Aciklama", "Para Birimi", "Borsa", "Fiyat", "Degisim (%)",
               "Getiri (1 Hafta)", "Getiri (1 Ay)", "Getiri (3 Ay)", "Getiri (1 Yil)"],
}


def _piyasa_rapor_olustur(goruntu: str, tip: str, piyasa: dict, teknik: dict) -> list:
    """Piyasa + teknik verilerden HTML mesaj listesi üretir."""
    emoji_tip  = _TIP_EMOJI.get(tip, "📊")
    baslik_tip = _TIP_BASLIK.get(tip, tip.upper())

    # Başlık
    rapor = f"{emoji_tip} <b>{_html(goruntu)} — {baslik_tip}</b>\n"
    rapor += "━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Genel bilgiler
    anahtarlar = GENEL_ANAHTARLAR.get(tip, [])
    satirlar = []
    for k in anahtarlar:
        v = piyasa.get(k)
        if v and str(v) not in ("", "N/A", "0", "None"):
            satirlar.append(f"  {k:<28}: {_html(str(v))}")
    if satirlar:
        rapor += f"<b>ℹ️ Genel Bilgiler</b>\n<pre>{chr(10).join(satirlar)}</pre>\n\n"

    mesajlar = [rapor]

    # Teknik analiz
    if teknik and "Hata" not in teknik:
        MA_KEYS = {"SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"}

        tek_blok = bolum_olustur_html(
            "TEKNİK ANALİZ İNDİKATÖRLERİ", "📉", teknik,
            filtre_fn=lambda k: k not in MA_KEYS
        )
        if tek_blok:
            mesajlar.append(tek_blok)

        ma_satirlar = []
        for ma_tip in ("SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"):
            if ma_tip in teknik:
                ma_satirlar.append(f"{ma_tip.split()[0]}: {teknik[ma_tip]}")
        if ma_satirlar:
            mesajlar.append(bolum_olustur_html_liste("HAREKETLİ ORTALAMALAR", "🌊", ma_satirlar))

    return mesajlar


def _piyasa_isle(chat_id: int, mesaj_id: int, girdi: str, tip: str):
    try:
        if tip == "kripto":
            piyasa, teknik = kripto_analiz(girdi)
        elif tip == "doviz":
            piyasa, teknik = doviz_analiz(girdi)
        else:
            piyasa, teknik = emtia_analiz(girdi)

        if "Hata" in piyasa:
            bot.edit_message_text(f"❌ {_html(piyasa['Hata'])}",
                                  chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
            return

        goruntu  = piyasa.get("_goruntu", girdi)
        mesajlar = _piyasa_rapor_olustur(goruntu, tip, piyasa, teknik)

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
            bot.edit_message_text(f"❌ Hata: {_html(str(e))}",
                                  chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, f"❌ Hata: {_html(str(e))}", parse_mode="HTML")


def _piyasa_ai_isle(chat_id: int, mesaj_id: int, girdi: str, tip: str):
    try:
        if tip == "kripto":
            piyasa, teknik = kripto_analiz(girdi)
        elif tip == "doviz":
            piyasa, teknik = doviz_analiz(girdi)
        else:
            piyasa, teknik = emtia_analiz(girdi)

        if "Hata" in piyasa:
            bot.edit_message_text(f"❌ {_html(piyasa['Hata'])}",
                                  chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
            return

        goruntu  = piyasa.get("_goruntu", girdi)
        mesajlar = _piyasa_rapor_olustur(goruntu, tip, piyasa, teknik)

        for i, msg in enumerate(mesajlar):
            if i == 0:
                try:
                    bot.edit_message_text(msg, chat_id=chat_id,
                                          message_id=mesaj_id, parse_mode="HTML")
                except Exception:
                    bot.send_message(chat_id, msg, parse_mode="HTML")
            else:
                bot.send_message(chat_id, msg, parse_mode="HTML")

        # AI yorumu
        bot.send_message(chat_id, "🤖 <b>AI analiz yorumu hazırlanıyor...</b>", parse_mode="HTML")
        yorum     = ai_piyasa_yorumu(girdi, tip, piyasa, teknik)
        emoji_tip = _TIP_EMOJI.get(tip, "📊")
        baslik    = f"{emoji_tip} <b>AI ANALİST — {_html(goruntu)}</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        tam_metin = baslik + _html(yorum)
        for parca in _parcala_html(tam_metin, limit=4000):
            bot.send_message(chat_id, parca, parse_mode="HTML")

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Hata: {_html(str(e))}",
                                  chat_id=chat_id, message_id=mesaj_id, parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, f"❌ Hata: {_html(str(e))}", parse_mode="HTML")


# ─────────────────────────────────────────────
#  ANALİZ THREAD — BIST / yabancı hisseler
# ─────────────────────────────────────────────

def _analiz_isle(chat_id: int, mesaj_id: int, hisse_kodu: str, komut: str):
    try:
        temel_veriler  = {}
        teknik_veriler = {}

        if komut in ("analiz", "ai"):
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_temel  = ex.submit(temel_analiz_yap, hisse_kodu)
                f_teknik = ex.submit(teknik_analiz_yap, hisse_kodu)
                temel_veriler  = f_temel.result()
                teknik_veriler = f_teknik.result()
        elif komut == "temel":
            temel_veriler = temel_analiz_yap(hisse_kodu)
        elif komut == "teknik":
            teknik_veriler = teknik_analiz_yap(hisse_kodu)

        if temel_veriler and "Hata" in temel_veriler:
            _gonder_html(chat_id, mesaj_id, f"❌ {_html(temel_veriler['Hata'])}")
            return
        if teknik_veriler and "Hata" in teknik_veriler:
            _gonder_html(chat_id, mesaj_id, f"❌ {_html(teknik_veriler['Hata'])}")
            return

        # ── Temel Analiz Raporu ───────────────────────────────────────────
        if temel_veriler:
            rapor = (f"📊 <b>{_html(hisse_kodu)} — TEMEL ANALİZ</b>\n"
                     f"━━━━━━━━━━━━━━━━━━━━━\n\n")

            genel = bolum_olustur_html(
                "Genel Bilgiler", "ℹ️", temel_veriler,
                filtre_fn=lambda k: k in (
                    "Firma Sektörü", "Çalışan Sayısı", "Para Birimi",
                    "Borsa", "Bilanço Dönemi", "Son Çeyrek Dönemi"
                )
            )
            if genel:
                rapor += genel + "\n\n"

            for (ad, emoji), fn in TEMEL_GRUPLAR.items():
                blok = bolum_olustur_html(ad, emoji, temel_veriler, filtre_fn=fn)
                if blok:
                    rapor += blok + "\n\n"

            _gonder_html(chat_id, mesaj_id, rapor.strip(), duzenle=True)

        # ── Teknik Analiz Raporu ──────────────────────────────────────────
        if teknik_veriler:
            MA_KEYS = {"SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"}

            tek_blok = bolum_olustur_html(
                "TEKNİK ANALİZ İNDİKATÖRLERİ", "📉", teknik_veriler,
                filtre_fn=lambda k: k not in MA_KEYS
            )
            duzenle_teknik = not bool(temel_veriler)
            _gonder_html(chat_id, mesaj_id, tek_blok, duzenle=duzenle_teknik)

            ma_satirlar = []
            for ma_tip in ("SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"):
                if ma_tip in teknik_veriler:
                    ma_satirlar.append(f"{ma_tip.split()[0]}: {teknik_veriler[ma_tip]}")
            if ma_satirlar:
                ma_blok = bolum_olustur_html_liste("HAREKETLİ ORTALAMALAR", "🌊", ma_satirlar)
                bot.send_message(chat_id, ma_blok, parse_mode="HTML")

        # ── AI Yorumu (/ai) ───────────────────────────────────────────────
        if komut == "ai" and temel_veriler and teknik_veriler:
            bot.send_message(chat_id,
                "🤖 <b>AI Analist yorumu hazırlanıyor...</b>", parse_mode="HTML")
            yorum = ai_analist_yorumu(hisse_kodu, temel_veriler, teknik_veriler)
            baslik = (f"🤖 <b>AI ANALİST — {_html(hisse_kodu)}</b>\n"
                      f"━━━━━━━━━━━━━━━━━━━━━\n\n")
            tam_metin = baslik + _html(yorum)
            for parca in _parcala_html(tam_metin, limit=4000):
                bot.send_message(chat_id, parca, parse_mode="HTML")

    except Exception as e:
        hata = f"❌ <b>Sistem Hatası</b>\n<code>{_html(str(e))}</code>"
        try:
            _gonder_html(chat_id, mesaj_id, hata, duzenle=True)
        except Exception:
            bot.send_message(chat_id, hata, parse_mode="HTML")


# ─────────────────────────────────────────────
#  BAŞLAT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    baslangic_temizligi()
    print(f"[{datetime.now():%H:%M:%S}] 🧹 yFinance cache temizlendi")
    print(f"[{datetime.now():%H:%M:%S}] Bot başlatılıyor...")
    import time as _time
    while True:
        try:
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=30,
                restart_on_change=False,
                skip_pending=True,
            )
        except Exception as _e:
            print(f"[{datetime.now():%H:%M:%S}] ⚠️ Polling hatası: {_e} — 5sn sonra yeniden...")
            _time.sleep(5)
