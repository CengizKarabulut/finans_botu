import os
import re
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import telebot

from temel_analiz   import temel_analiz_yap
from teknik_analiz  import teknik_analiz_yap
from analist_motoru import ai_analist_yorumu

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
        "PEG Oranı (Günlük)", "Serbest Dolaşım/Float (%)"
    ),
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


_BILINEN_UZANTILAR = {".IS", ".L", ".PA", ".DE", ".HK", ".T", ".AX", ".TO", ".SW"}
_ABD_HISSELERI = {
    "AAPL","MSFT","GOOGL","GOOG","AMZN","NVDA","META","TSLA","BRK.A","BRK.B",
    "JPM","V","UNH","XOM","JNJ","WMT","MA","PG","HD","CVX","MRK","ABBV","PEP",
    "KO","BAC","AVGO","COST","TMO","CSCO","ACN","MCD","ABT","CRM","NFLX","LIN",
    "DHR","TXN","NEE","PM","AMD","QCOM","INTC","ORCL","IBM","GE","BA","CAT",
    "SPY","QQQ","VTI","IVV","GLD","SLV","USO","TLT","HYG",
}

def _normalize_ticker(ticker: str) -> str:
    """
    .IS olmadan gelen BIST hisselerine otomatik .IS ekler.
    AAPL, MSFT gibi bilinen ABD hisselerine dokunmaz.
    """
    ticker = ticker.upper().strip()
    for uzanti in _BILINEN_UZANTILAR:
        if ticker.endswith(uzanti):
            return ticker
    if ticker in _ABD_HISSELERI:
        return ticker
    if ticker.replace(".", "").isalnum():
        return ticker + ".IS"
    return ticker


def _parcala(metin: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    parcalar, mevcut = [], ""
    for satir in metin.splitlines(keepends=True):
        if len(mevcut) + len(satir) > limit:
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
        "Kullanım:\n"
        "`/analiz TUPRS` — Temel \\+ Teknik analiz\n"
        "`/temel THYAO` — Yalnızca temel analiz\n"
        "`/teknik ASELS` — Yalnızca teknik analiz\n"
        "`/ai ASELS` — 🤖 AI Analist Yorumu\n\n"
        "💡 \\.IS uzantısı opsiyonel \\— otomatik eklenir\\.\n"
        f"⏱ Sorgular arası en az {RATE_LIMIT_SANIYE} saniye bekleme uygulanır\\."
    )
    bot.reply_to(message, metin, parse_mode="MarkdownV2")


@bot.message_handler(commands=["analiz", "temel", "teknik", "ai"])
def komut_analiz(message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        bot.reply_to(
            message,
            "⚠️ Hisse kodu belirtin\\. Örnek: `/analiz ASELS`",
            parse_mode="MarkdownV2"
        )
        return

    hisse_kodu = _normalize_ticker(parcalar[1])
    komut      = parcalar[0].lstrip("/").lower()
    user_id    = message.from_user.id

    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        bot.reply_to(
            message,
            f"⏳ Lütfen *{bekleme}* saniye bekleyin\\.",
            parse_mode="MarkdownV2"
        )
        return

    _son_istek[user_id] = datetime.now()

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
            yorum = ai_analist_yorumu(hisse_kodu, temel_veriler, teknik_veriler)
            bot.send_message(chat_id, "AI ANALIST: " + hisse_kodu + "\n\n" + yorum, parse_mode=None)
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
    print(f"[{datetime.now():%H:%M:%S}] Bot başlatılıyor...")
    bot.infinity_polling(timeout=30, long_polling_timeout=20)
