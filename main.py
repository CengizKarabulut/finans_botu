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

_son_istek: dict[int, datetime] = {}
RATE_LIMIT_SANIYE = 15
TELEGRAM_LIMIT    = 4096

TEMEL_GRUPLAR = {
    ("Piyasa Verileri",    "💹"): lambda k: k in (
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
    ("Değerleme",          "🏷"): lambda k: k in (
        "F/K (Hesaplanan)", "PD/DD (Hesaplanan)", "F/S (Fiyat/Satış)",
        "EV/EBITDA (Hesaplanan)", "EV/EBIT", "EV/Sales", "PEG Oranı (Hesaplanan)"
    ),
    ("Karlılık — Yıllık",  "📈"): lambda k: "Yıllık" in k and any(
        x in k for x in ["Marjı", "Karlılık", "ROE", "ROA", "ROIC"]
    ) or k == "ROIC (%)",
    ("Karlılık — Çeyreklik", "📊"): lambda k: "Çeyreklik" in k and any(
        x in k for x in ["Marjı", "Karlılık"]
    ),
    ("Büyüme",             "🚀"): lambda k: "Büyüme" in k or k == "EPS Büyümesi — Yıllık (%)",
    ("Likidite",           "💧"): lambda k: k in (
        "Cari Oran", "Likidite Oranı (Hızlı)", "Nakit Oranı"
    ),
    ("Borç / Kaldıraç",    "🏦"): lambda k: k in (
        "Borç / Özsermaye (D/E)", "Finansal Borç / Özsermaye (%)",
        "Net Borç / FAVÖK", "Faiz Karşılama Oranı", "Finansal Borç / Varlık (%)"
    ),
    ("Faaliyet Etkinliği", "⚙️"): lambda k: k in (
        "Varlık Devir Hızı", "Stok Devir Hızı", "Alacak Devir Hızı",
        "Stok Günü (DSI)", "Alacak Günü (DSO)"
    ),
    ("Nakit Akışı",        "💵"): lambda k: k in (
        "FCF (Serbest Nakit Akışı)", "FCF Getirisi (%)", "FCF / Net Kar",
        "Temettü Verimi (%)", "Temettü Ödeme Oranı (%)"
    ),
}

# ─────────────────────────────────────────────
#  YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def escape_md(text: str) -> str:
    """MarkdownV2 için özel karakterleri escape eder."""
    return re.sub(r"([_\*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", str(text))


# Bilinen borsa uzantıları — bunlar gelirse dokunma
_BILINEN_UZANTILAR = {
    ".IS", ".L", ".PA", ".DE", ".MI", ".AS", ".BR", ".MC", ".SW",
    ".HK", ".T", ".SS", ".SZ", ".KS", ".KQ", ".AX", ".TO", ".V",
    ".SA", ".MX", ".NS", ".BO",
}

# Sembol normalize cache (process boyunca geçerli, 2. sorguda anında döner)
_TICKER_CACHE: dict = {}


def _normalize_ticker(ticker: str) -> str:
    """
    Akıllı sembol çözümleme:
    1. Zaten uzantısı varsa (.L, .DE vb.) → olduğu gibi kullan
    2. Cache'te varsa → cache'teki sonucu kullan
    3. yFinance'ta direkt çalışıyorsa (ABD hissesi vb.) → direkt kullan
    4. .IS eklenince çalışıyorsa → .IS ekle
    5. Hiçbiri değilse → .IS ekle (BIST varsayımı)
    """
    import yfinance as yf

    ticker = ticker.upper().strip()

    # 1. Bilinen uzantı varsa dokunma
    for uzanti in _BILINEN_UZANTILAR:
        if ticker.endswith(uzanti):
            return ticker

    # 2. Cache'te varsa
    if ticker in _TICKER_CACHE:
        return _TICKER_CACHE[ticker]

    # 3. Direkt dene (ABD / ETF vb.)
    try:
        info = yf.Ticker(ticker).fast_info
        fiyat = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        if fiyat and float(fiyat) > 0:
            _TICKER_CACHE[ticker] = ticker
            return ticker
    except Exception:
        pass

    # 4. .IS ekleyerek dene
    ticker_is = ticker + ".IS"
    try:
        info = yf.Ticker(ticker_is).fast_info
        fiyat = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        if fiyat and float(fiyat) > 0:
            _TICKER_CACHE[ticker] = ticker_is
            return ticker_is
    except Exception:
        pass

    # 5. Varsayılan: .IS ekle
    _TICKER_CACHE[ticker] = ticker_is
    return ticker_is


def _parcala(metin: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """
    Metni Telegram limitini aşmayacak parçalara böler.
    Önce satır sınırına, satır limitten uzunsa kelime sınırına göre keser.
    Markdown kod bloklarında ``` açık/kapalı dengesini korur.
    """
    def _kes(uzun_satir: str) -> list[str]:
        """Tek bir uzun satırı kelime sınırında böler."""
        parcalar, i = [], 0
        while i < len(uzun_satir):
            uc = i + limit
            if uc >= len(uzun_satir):
                parcalar.append(uzun_satir[i:])
                break
            # Geriye doğru en yakın boşluk veya noktalama bul
            kesim = uzun_satir.rfind(" ", i, uc)
            if kesim == -1:
                kesim = uc   # boşluk yoksa zorla kes
            parcalar.append(uzun_satir[i:kesim])
            i = kesim + 1
        return parcalar

    satirlar = metin.splitlines(keepends=True)
    parcalar, mevcut = [], ""

    for satir in satirlar:
        # Satır tek başına zaten limitten uzunsa parçala
        if len(satir) > limit:
            if mevcut.strip():
                parcalar.append(mevcut)
                mevcut = ""
            for alt in _kes(satir):
                parcalar.append(alt)
            continue

        if len(mevcut) + len(satir) > limit:
            # Kod bloğu açıkta kaldıysa kapat
            if mevcut.count("```") % 2 == 1:
                mevcut += "```"
                parcalar.append(mevcut)
                mevcut = "```\n" + satir
            else:
                parcalar.append(mevcut)
                mevcut = satir
        else:
            mevcut += satir

    if mevcut.strip():
        parcalar.append(mevcut)

    return parcalar


def bolum_olustur(baslik: str, emoji: str, veriler: dict,
                  filtre_fn=None, kolon_genislik: int = 36) -> str:
    satirlar = []
    for k, v in veriler.items():
        if k.startswith("_"):
            continue
        if filtre_fn and not filtre_fn(k):
            continue
        if isinstance(v, float):
            if abs(v) >= 1_000_000_000_000:
                v_str = f"{v/1_000_000_000_000:.2f}T"
            elif abs(v) >= 1_000_000_000:
                v_str = f"{v/1_000_000_000:.2f}B"
            elif abs(v) >= 1_000_000:
                v_str = f"{v/1_000_000:.2f}M"
            else:
                v_str = f"{v:,.2f}"
        elif isinstance(v, int) and abs(v) > 1_000_000_000_000:
            v_str = f"{v/1_000_000_000_000:.2f}T"
        elif isinstance(v, int) and abs(v) > 1_000_000_000:
            v_str = f"{v/1_000_000_000:.2f}B"
        elif isinstance(v, int) and abs(v) > 1_000_000:
            v_str = f"{v/1_000_000:.2f}M"
        else:
            v_str = str(v)
        satirlar.append(f"{k:<{kolon_genislik}} : {v_str}")
    if not satirlar:
        return ""
    icerik = "\n".join(satirlar)
    return f"{emoji} *{escape_md(baslik)}*\n```\n{icerik}\n```"


def mesaj_gonder(chat_id: int, mesaj_id: int, metin: str, duzenle: bool = True):
    for i, parca in enumerate(_parcala(metin)):
        try:
            if i == 0 and duzenle:
                bot.edit_message_text(
                    parca, chat_id=chat_id, message_id=mesaj_id,
                    parse_mode="MarkdownV2"
                )
            else:
                bot.send_message(chat_id, parca, parse_mode="MarkdownV2")
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                bot.send_message(chat_id, parca, parse_mode="MarkdownV2")


def rate_limit_kontrol(user_id: int) -> int:
    son = _son_istek.get(user_id)
    if son is None:
        return 0
    gecen = (datetime.now() - son).total_seconds()
    return max(0, int(RATE_LIMIT_SANIYE - gecen))


# ─────────────────────────────────────────────
#  KOMUT İŞLEYİCİLER
# ─────────────────────────────────────────────

@bot.message_handler(commands=["start", "yardim"])
def komut_yardim(message):
    metin = (
        "📈 *Finans Asistanı*\n\n"

        "🇹🇷 *BIST Hisseleri:*\n"
        "`/analiz TUPRS` — Temel \\+ Teknik analiz\\n"
        "`/temel THYAO` — Yalnızca temel analiz\\n"
        "`/teknik ASELS` — Yalnızca teknik analiz\\n"
        "`/ai ASELS` — 🤖 AI Analist Yorumu\\n\\n"

        "🌍 *Yabancı Hisseler:*\n"
        "`/analiz AAPL` — Temel \\+ Teknik \\(ABD\\)\\n"
        "`/teknik SHEL\\.L` — Yalnızca teknik \\(Londra\\)\\n"
        "`/ai SAP\\.DE` — AI Yorum \\(Frankfurt\\)\\n"
        "Borsa uzantıları: \\.L \\.DE \\.PA \\.HK \\.T \\.AX vb\\.\\n\\n"

        "₿ *Kripto:*\n"
        "`/kripto BTC` — Bitcoin \\(USD\\)\\n"
        "`/kripto ETHTRY` — Ethereum \\(TRY\\)\\n"
        "`/ai BTC` — AI Kripto Yorumu\\n"
        "`/kripto liste` — Tüm desteklenen kriptolar\\n\\n"

        "💱 *Döviz:*\n"
        "`/doviz USDTRY` — Dolar/TL\\n"
        "`/doviz EURUSD` — Euro/Dolar\\n"
        "`/ai USDTRY` — AI Döviz Yorumu\\n"
        "`/doviz liste` — Tüm pariteler\\n\\n"

        "🏭 *Emtia:*\n"
        "`/emtia ALTIN` — Altın vadeli\\n"
        "`/emtia PETROL` — Ham petrol\\n"
        "`/ai ALTIN` — AI Emtia Yorumu\\n"
        "`/emtia liste` — Tüm emtialar\\n\\n"

        "💡 BIST için \\.IS uzantısı opsiyonel \\— otomatik eklenir\\.\n"
        f"⏱ Sorgular arası en az {RATE_LIMIT_SANIYE} saniye bekleme uygulanır\\."
    )
    bot.reply_to(message, metin, parse_mode="MarkdownV2")


@bot.message_handler(commands=["analiz", "temel", "teknik", "ai"])
def komut_analiz(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(
            message,
            "⚠️ Sembol belirtin\\. Örnek: `/analiz ASELS` veya `/ai BTC`",
            parse_mode="MarkdownV2"
        )
        return

    girdi  = parcalar[1].upper().strip()
    komut  = parcalar[0].lstrip("/").lower()
    user_id = message.from_user.id

    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ Lütfen *{bekleme}* saniye bekleyin\\.", parse_mode="MarkdownV2")
        return
    _son_istek[user_id] = datetime.now()

    # Piyasa tipi algıla
    from piyasa_analiz import KRIPTO_MAP, DOVIZ_MAP, EMTIA_MAP
    piyasa_tip = None
    if girdi in KRIPTO_MAP or girdi.endswith("-USD") or girdi.endswith("-TRY"):
        piyasa_tip = "kripto"
    elif girdi in DOVIZ_MAP or girdi.endswith("=X"):
        piyasa_tip = "doviz"
    elif girdi in EMTIA_MAP or girdi.endswith("=F"):
        piyasa_tip = "emtia"

    # Kripto/döviz/emtia → /ai, /teknik, /temel hepsi piyasa akışına yönlendir
    if piyasa_tip:
        if komut == "temel":
            # Temel veri yok, piyasa genel bilgisi göster
            bot.reply_to(message,
                f"ℹ️ {girdi} için temel finansal veri yok\\. `/emtia`, `/kripto` veya `/doviz` komutunu kullanın\\.",
                parse_mode="MarkdownV2")
            return

        bekle_msg = bot.reply_to(
            message,
            f"⏳ *{escape_md(girdi)}* analiz ediliyor\\.\\.\\.",
            parse_mode="MarkdownV2"
        )
        if komut == "ai":
            threading.Thread(
                target=_piyasa_ai_isle,
                args=(message.chat.id, bekle_msg.message_id, girdi, piyasa_tip),
                daemon=True
            ).start()
        else:
            threading.Thread(
                target=_piyasa_isle,
                args=(message.chat.id, bekle_msg.message_id, girdi, piyasa_tip),
                daemon=True
            ).start()
        return

    # BIST / yabancı hisse normal akış
    hisse_kodu = _normalize_ticker(girdi)
    bekle_msg = bot.reply_to(
        message,
        f"⏳ *{escape_md(hisse_kodu)}* verileri işleniyor\\.\\.\\.",
        parse_mode="MarkdownV2"
    )
    threading.Thread(
        target=_analiz_isle,
        args=(message.chat.id, bekle_msg.message_id, hisse_kodu, komut),
        daemon=True
    ).start()


@bot.message_handler(commands=["kripto"])
def komut_kripto(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message, "⚠️ Örnek: /kripto BTC veya /kripto liste", parse_mode=None)
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message, f"₿ Desteklenen kriptolar:\n{KRIPTO_LISTE}", parse_mode=None)
        return
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ Lütfen {bekleme} saniye bekleyin.", parse_mode=None)
        return
    _son_istek[user_id] = datetime.now()
    bekle_msg = bot.reply_to(message, f"⏳ {girdi} verileri çekiliyor...", parse_mode=None)
    threading.Thread(
        target=_piyasa_isle,
        args=(message.chat.id, bekle_msg.message_id, girdi, "kripto"),
        daemon=True
    ).start()


@bot.message_handler(commands=["doviz"])
def komut_doviz(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message, "⚠️ Örnek: /doviz USDTRY veya /doviz liste", parse_mode=None)
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message, f"💱 Desteklenen pariteler:\n{DOVIZ_LISTE}", parse_mode=None)
        return
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ Lütfen {bekleme} saniye bekleyin.", parse_mode=None)
        return
    _son_istek[user_id] = datetime.now()
    bekle_msg = bot.reply_to(message, f"⏳ {girdi} verileri çekiliyor...", parse_mode=None)
    threading.Thread(
        target=_piyasa_isle,
        args=(message.chat.id, bekle_msg.message_id, girdi, "doviz"),
        daemon=True
    ).start()


@bot.message_handler(commands=["emtia"])
def komut_emtia(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(message, "⚠️ Örnek: /emtia ALTIN veya /emtia liste", parse_mode=None)
        return
    girdi = parcalar[1].upper()
    if girdi == "LISTE":
        bot.reply_to(message, f"🏭 Desteklenen emtialar:\n{EMTIA_LISTE}", parse_mode=None)
        return
    user_id = message.from_user.id
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(message, f"⏳ Lütfen {bekleme} saniye bekleyin.", parse_mode=None)
        return
    _son_istek[user_id] = datetime.now()
    bekle_msg = bot.reply_to(message, f"⏳ {girdi} verileri çekiliyor...", parse_mode=None)
    threading.Thread(
        target=_piyasa_isle,
        args=(message.chat.id, bekle_msg.message_id, girdi, "emtia"),
        daemon=True
    ).start()


# ─────────────────────────────────────────────
#  PİYASA ANALİZ THREAD (kripto/döviz/emtia)
# ─────────────────────────────────────────────

# Emoji ve başlık haritası
_TIP_EMOJI  = {"kripto": "₿", "doviz": "💱", "emtia": "🏭"}
_TIP_BASLIK = {"kripto": "KRİPTO", "doviz": "DÖVİZ", "emtia": "EMTİA"}

# Gösterilmeyecek iç anahtarlar
_GİZLİ = {"_tip", "_sembol", "_goruntu"}


def _piyasa_bolum(baslik: str, emoji: str, veriler: dict, anahtarlar: list) -> str:
    satirlar = []
    for k in anahtarlar:
        v = veriler.get(k)
        if v is not None and v != "" and v != "N/A" and v != "0" and v != 0:
            satirlar.append(f"{k:<28} : {v}")
    if not satirlar:
        return ""
    icerik = "\n".join(satirlar)
    return f"{emoji} *{escape_md(baslik)}*\n```\n{icerik}\n```"


def _piyasa_isle(chat_id: int, mesaj_id: int, girdi: str, tip: str):
    try:
        if tip == "kripto":
            piyasa, teknik = kripto_analiz(girdi)
        elif tip == "doviz":
            piyasa, teknik = doviz_analiz(girdi)
        else:
            piyasa, teknik = emtia_analiz(girdi)

        # Hata kontrolü
        if "Hata" in piyasa:
            bot.edit_message_text(
                f"❌ {piyasa['Hata']}",
                chat_id=chat_id, message_id=mesaj_id, parse_mode=None
            )
            return

        emoji_tip  = _TIP_EMOJI.get(tip, "📊")
        baslik_tip = _TIP_BASLIK.get(tip, tip.upper())
        goruntu    = piyasa.get("_goruntu", girdi)

        # ── Piyasa Bilgisi Raporu ──────────────────────────────────────────
        GENEL_ANAHTARLAR = {
            "kripto": ["Isim", "Para Birimi", "Fiyat", "Degisim (%)",
                       "Piyasa Degeri", "Hacim (24s)", "Dolasim Arzi", "Maks Arz"],
            "doviz":  ["Parite", "Aciklama", "Fiyat", "Degisim (%)",
                       "Getiri (1 Hafta)", "Getiri (1 Ay)", "Getiri (3 Ay)", "Getiri (1 Yil)"],
            "emtia":  ["Aciklama", "Para Birimi", "Borsa", "Fiyat", "Degisim (%)",
                       "Getiri (1 Hafta)", "Getiri (1 Ay)", "Getiri (3 Ay)", "Getiri (1 Yil)"],
        }
        rapor = f"{emoji_tip} *{escape_md(goruntu)} — {baslik_tip} ANALİZİ*\n\n"
        genel_blok = _piyasa_bolum("Genel Bilgiler", "ℹ️", piyasa,
                                    GENEL_ANAHTARLAR.get(tip, []))
        if genel_blok:
            rapor += genel_blok + "\n\n"

        # İlk mesajı gönder
        for i, parca in enumerate(_parcala(rapor.strip())):
            try:
                if i == 0:
                    bot.edit_message_text(parca, chat_id=chat_id,
                                          message_id=mesaj_id, parse_mode="MarkdownV2")
                else:
                    bot.send_message(chat_id, parca, parse_mode="MarkdownV2")
            except Exception:
                bot.send_message(chat_id, parca, parse_mode="MarkdownV2")

        # ── Teknik Analiz (teknik_analiz.py'nin tam çıktısı) ──────────────
        if teknik and "Hata" not in teknik:
            MA_ANAHTARLARI = {"SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"}
            indikatörler = bolum_olustur(
                "TEKNİK ANALİZ İNDİKATÖRLERİ", "📉",
                teknik,
                filtre_fn=lambda k: k not in MA_ANAHTARLARI
            )
            ma_satirlar = []
            for ma_tip in ("SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"):
                if ma_tip in teknik:
                    ma_satirlar.append(f"{ma_tip.split()[0]}: {teknik[ma_tip]}")
            ma_blok = "🌊 *HAREKETLİ ORTALAMALAR*\n```\n" + "\n\n".join(ma_satirlar) + "\n```"

            mesaj_gonder(chat_id, mesaj_id, indikatörler, duzenle=False)
            bot.send_message(chat_id, ma_blok, parse_mode="MarkdownV2")

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Hata: {str(e)}",
                                  chat_id=chat_id, message_id=mesaj_id, parse_mode=None)
        except Exception:
            bot.send_message(chat_id, f"❌ Hata: {str(e)}", parse_mode=None)


def _piyasa_ai_isle(chat_id: int, mesaj_id: int, girdi: str, tip: str):
    """Kripto/döviz/emtia için önce teknik+piyasa çeker, sonra AI yorumu üretir."""
    try:
        if tip == "kripto":
            piyasa, teknik = kripto_analiz(girdi)
        elif tip == "doviz":
            piyasa, teknik = doviz_analiz(girdi)
        else:
            piyasa, teknik = emtia_analiz(girdi)

        if "Hata" in piyasa:
            bot.edit_message_text(f"❌ {piyasa['Hata']}",
                                  chat_id=chat_id, message_id=mesaj_id, parse_mode=None)
            return

        # Önce piyasa + teknik raporu gönder
        emoji_tip  = _TIP_EMOJI.get(tip, "📊")
        baslik_tip = _TIP_BASLIK.get(tip, tip.upper())
        goruntu    = piyasa.get("_goruntu", girdi)

        GENEL_ANAHTARLAR = {
            "kripto": ["Isim", "Para Birimi", "Fiyat", "Degisim (%)",
                       "Piyasa Degeri", "Hacim (24s)", "Dolasim Arzi", "Maks Arz"],
            "doviz":  ["Parite", "Aciklama", "Fiyat", "Degisim (%)",
                       "Getiri (1 Hafta)", "Getiri (1 Ay)", "Getiri (3 Ay)", "Getiri (1 Yil)"],
            "emtia":  ["Aciklama", "Para Birimi", "Borsa", "Fiyat", "Degisim (%)",
                       "Getiri (1 Hafta)", "Getiri (1 Ay)", "Getiri (3 Ay)", "Getiri (1 Yil)"],
        }
        rapor = f"{emoji_tip} *{escape_md(goruntu)} — {baslik_tip} ANALİZİ*\n\n"
        genel_blok = _piyasa_bolum("Genel Bilgiler", "ℹ️", piyasa, GENEL_ANAHTARLAR.get(tip, []))
        if genel_blok:
            rapor += genel_blok + "\n\n"

        for i, parca in enumerate(_parcala(rapor.strip())):
            try:
                if i == 0:
                    bot.edit_message_text(parca, chat_id=chat_id,
                                          message_id=mesaj_id, parse_mode="MarkdownV2")
                else:
                    bot.send_message(chat_id, parca, parse_mode="MarkdownV2")
            except Exception:
                bot.send_message(chat_id, parca, parse_mode="MarkdownV2")

        # Teknik analiz
        if teknik and "Hata" not in teknik:
            MA_ANAHTARLARI = {"SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"}
            indikatörler = bolum_olustur("TEKNİK ANALİZ İNDİKATÖRLERİ", "📉", teknik,
                                          filtre_fn=lambda k: k not in MA_ANAHTARLARI)
            ma_satirlar = []
            for ma_tip in ("SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"):
                if ma_tip in teknik:
                    ma_satirlar.append(f"{ma_tip.split()[0]}: {teknik[ma_tip]}")
            ma_blok = "🌊 *HAREKETLİ ORTALAMALAR*\n```\n" + "\n\n".join(ma_satirlar) + "\n```"
            mesaj_gonder(chat_id, mesaj_id, indikatörler, duzenle=False)
            bot.send_message(chat_id, ma_blok, parse_mode="MarkdownV2")

        # AI yorumu
        bot.send_message(chat_id, f"🤖 AI analiz yorumu hazırlanıyor...", parse_mode=None)
        yorum     = ai_piyasa_yorumu(girdi, tip, piyasa, teknik)
        tam_metin = f"AI ANALİST: {goruntu}\n\n{yorum}"
        for parca in _parcala(tam_metin, limit=4000):
            bot.send_message(chat_id, parca, parse_mode=None)

    except Exception as e:
        try:
            bot.edit_message_text(f"❌ Hata: {str(e)}",
                                  chat_id=chat_id, message_id=mesaj_id, parse_mode=None)
        except Exception:
            bot.send_message(chat_id, f"❌ Hata: {str(e)}", parse_mode=None)


# ─────────────────────────────────────────────
#  ANALİZ HESAPLAMA (THREAD)
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
            mesaj_gonder(chat_id, mesaj_id, f"❌ {escape_md(temel_veriler['Hata'])}")
            return
        if teknik_veriler and "Hata" in teknik_veriler:
            mesaj_gonder(chat_id, mesaj_id, f"❌ {escape_md(teknik_veriler['Hata'])}")
            return

        # ── Temel Analiz Raporu ───────────────────────────────────────────────
        if temel_veriler:
            rapor = f"📊 *{escape_md(hisse_kodu)} — TEMEL ANALİZ*\n\n"
            genel = bolum_olustur(
                "Genel Bilgiler", "ℹ️", temel_veriler,
                filtre_fn=lambda k: k in (
                    "Firma Sektörü", "Çalışan Sayısı", "Para Birimi",
                    "Borsa", "Bilanço Dönemi", "Son Çeyrek Dönemi"
                )
            )
            if genel:
                rapor += genel + "\n\n"
            for (ad, emoji), fn in TEMEL_GRUPLAR.items():
                blok = bolum_olustur(ad, emoji, temel_veriler, filtre_fn=fn)
                if blok:
                    rapor += blok + "\n\n"
            mesaj_gonder(chat_id, mesaj_id, rapor.strip(), duzenle=True)

        # ── Teknik Analiz Raporu ──────────────────────────────────────────────
        if teknik_veriler:
            MA_ANAHTARLARI = {"SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"}
            indikatörler = bolum_olustur(
                "TEKNİK ANALİZ İNDİKATÖRLERİ", "📉",
                teknik_veriler,
                filtre_fn=lambda k: k not in MA_ANAHTARLARI
            )
            ma_satirlar = []
            for tip in ("SMA (Basit)", "EMA (Üstel)", "WMA (Ağırlıklı)"):
                if tip in teknik_veriler:
                    ma_satirlar.append(f"{tip.split()[0]}: {teknik_veriler[tip]}")
            ma_blok = "🌊 *HAREKETLİ ORTALAMALAR*\n```\n" + "\n\n".join(ma_satirlar) + "\n```"
            duzenle_teknik = not bool(temel_veriler)
            mesaj_gonder(chat_id, mesaj_id, indikatörler, duzenle=duzenle_teknik)
            bot.send_message(chat_id, ma_blok, parse_mode="MarkdownV2")

        # AI Analist Yorumu (/ai)
        if komut == "ai" and temel_veriler and teknik_veriler:
            bot.send_message(chat_id, "AI Analist yorumu hazirlaniyor...", parse_mode=None)
            yorum     = ai_analist_yorumu(hisse_kodu, temel_veriler, teknik_veriler)
            tam_metin = "AI ANALIST: " + hisse_kodu + "\n\n" + yorum
            for parca in _parcala(tam_metin, limit=4000):
                bot.send_message(chat_id, parca, parse_mode=None)
    except Exception as e:
        hata = f"❌ *Sistem Hatası*\n`{escape_md(str(e))}`"
        try:
            mesaj_gonder(chat_id, mesaj_id, hata, duzenle=True)
        except Exception:
            bot.send_message(chat_id, hata, parse_mode="MarkdownV2")


# ─────────────────────────────────────────────
#  BAŞLAT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    baslangic_temizligi()
    print(f"[{datetime.now():%H:%M:%S}] 🧹 yFinance cache temizlendi")
    print(f"[{datetime.now():%H:%M:%S}] Bot başlatılıyor...")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)
