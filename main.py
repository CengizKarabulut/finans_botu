"""
main.py — Finans Botu Ana Giriş Noktası
✅ MİMARİ GÜNCELLEME - Zeki Sembol Doğrulama ve Advanced Graceful Shutdown.
✅ DÜZELTİLDİ - Dispatcher tanımı düzeltildi, tüm komutlar ve callback handler'lar eklendi.
"""
import os
import asyncio
import logging
import signal
import sys
from functools import partial
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.client.default import DefaultBotProperties

# ═══════════════════════════════════════════════════════════════
# IMPORTLAR
# ═══════════════════════════════════════════════════════════════
from config import settings, validate_startup
from security.input_validator import validate_symbol, sanitize_text, validate_numeric
from security.rate_limiter import limiter
from security.audit_logger import setup_audit_logging, log_query, log_security_event
from ux.inline_menus import build_analiz_menu, build_close_button
from ux.i18n import get_text

from temel_analiz import temel_analiz_yap
from teknik_analiz import teknik_analiz_yap
from analist_motoru import ai_analist_yorumu, ai_tahmin_yap, ai_nlp_sorgu
from db import (
    db_init, kullanici_kaydet, close_db,
    favori_ekle, favori_sil, favori_toggle, favorileri_getir,
    uyari_ekle, kullanici_uyarilari_getir, uyari_sil,
    kullanici_dil_getir
)
from alert_motoru import uyari_kontrol_dongusu
from tradingview_motoru import tv_grafik_cek, TVBrowser
from portfoy_motoru import portfoy_ozeti_hazirla, portfoy_varlik_ekle, portfoy_varlik_sil
from cache_yonetici import baslangic_temizligi

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            os.path.join(LOG_DIR, "bot.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
    ]
)
log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════
# BOT & DISPATCHER (Global)
# ═══════════════════════════════════════════════════════════════
bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ═══════════════════════════════════════════════════════════════
# GRACEFUL SHUTDOWN
# ═══════════════════════════════════════════════════════════════

async def shutdown(loop, sig=None):
    """Botu ve aktif görevleri temiz bir şekilde kapatır."""
    if sig:
        log.info(f"🛑 Kapatma sinyali alındı: {sig.name}")

    log.info("⏳ Aktif görevler iptal ediliyor...")
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]

    await asyncio.gather(*tasks, return_exceptions=True)

    log.info("🔌 Kaynaklar serbest bırakılıyor...")
    await close_db()
    await TVBrowser.close()

    log.info("✅ Bot başarıyla kapatıldı.")
    loop.stop()
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════
# YARDIMCILAR
# ═══════════════════════════════════════════════════════════════

async def _async(func, *args, **kwargs):
    """Senkron fonksiyonu asenkron olarak çalıştırır."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


async def _rate_limit_check(message: Message) -> bool:
    """Rate limit kontrolü yapar. True ise devam et, False ise engelle."""
    allowed, wait_time = await limiter.check(message.from_user.id)
    if not allowed:
        log_security_event(
            message.from_user.id,
            "RATE_LIMIT",
            f"Rate limit aşıldı: {message.from_user.id}",
            severity="low"
        )
        await message.reply(
            f"⏱️ Çok fazla istek gönderdiniz. Lütfen <b>{wait_time}</b> saniye bekleyin."
        )
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# KOMUTLAR
# ═══════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def komut_start(message: Message):
    """Bot başlangıç komutu."""
    await kullanici_kaydet(message.from_user.id, message.from_user.username or "")
    lang = await kullanici_dil_getir(message.from_user.id)
    welcome = get_text('welcome', lang)
    await message.reply(welcome)


@dp.message(Command("yardim"))
@dp.message(Command("help"))
async def komut_yardim(message: Message):
    """Yardım mesajı."""
    yardim = (
        "📖 <b>Finans Botu Komutları</b>\n\n"
        "<b>📊 Analiz Komutları:</b>\n"
        "• <code>/analiz THYAO</code> — Kapsamlı analiz\n"
        "• <code>/temel AAPL</code> — Temel analiz\n"
        "• <code>/teknik BTCUSD</code> — Teknik analiz\n"
        "• <code>/tahmin MSFT</code> — AI fiyat tahmini\n"
        "• <code>/grafik THYAO</code> — TradingView grafiği\n\n"
        "<b>🔔 Uyarı Komutları:</b>\n"
        "• <code>/uyari THYAO fiyat_ust 50</code> — Fiyat uyarısı\n"
        "• <code>/uyari THYAO rsi_alt 30</code> — RSI uyarısı\n"
        "• <code>/uyarilarim</code> — Aktif uyarılarınız\n\n"
        "<b>💼 Portföy Komutları:</b>\n"
        "• <code>/portfoy</code> — Portföy özeti\n"
        "• <code>/portfoy_ekle THYAO 100 45.50</code> — Varlık ekle\n"
        "• <code>/portfoy_sil THYAO</code> — Varlık sil\n\n"
        "<b>⭐ Favori Komutları:</b>\n"
        "• <code>/favoriler</code> — Favori listeniz\n"
        "• <code>/favori_ekle THYAO</code> — Favoriye ekle\n"
        "• <code>/favori_sil THYAO</code> — Favoriden çıkar\n\n"
        "<b>📈 Piyasa Komutları:</b>\n"
        "• <code>/trend</code> — Popüler varlıklar\n\n"
        "💡 <i>Herhangi bir metin yazarak AI asistanımla sohbet edebilirsiniz.</i>"
    )
    await message.reply(yardim)


@dp.message(Command("analiz"))
async def komut_analiz(message: Message):
    """Kapsamlı analiz komutu."""
    if not await _rate_limit_check(message):
        return

    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Örnek: <code>/analiz THYAO</code>")
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, tip = validate_symbol(girdi)

    if not valid:
        await message.reply("❌ Geçersiz sembol formatı. Örnek: THYAO, AAPL, BTCUSD")
        return

    log_query(message.from_user.id, message.from_user.username or "", sembol, "analiz")
    bekle_msg = await message.reply(f"⏳ <b>{sembol}</b> ({tip}) verileri işleniyor...")

    try:
        temel_v, teknik_v = await asyncio.gather(
            _async(temel_analiz_yap, sembol),
            _async(teknik_analiz_yap, sembol)
        )

        if ("Hata" in temel_v or not temel_v) and ("Hata" in teknik_v or not teknik_v):
            await bekle_msg.edit_text(f"❌ Veri bulunamadı: <b>{sembol}</b>")
            return

        fiyat = temel_v.get("Fiyat", teknik_v.get("Güncel Fiyat", "—"))
        degisim = temel_v.get("Günlük Değişim (%)", "—")
        rsi = teknik_v.get("RSI (14)", "—")

        rapor = (
            f"📊 <b>{sembol} Analiz Özeti</b>\n"
            f"💰 Fiyat: <b>{fiyat}</b>\n"
            f"📈 Değişim: <b>{degisim}</b>\n"
            f"📉 RSI (14): <b>{rsi}</b>\n\n"
            f"Detaylı analiz için aşağıdaki butonları kullanabilirsiniz."
        )

        reply_markup = build_analiz_menu(sembol)
        await bekle_msg.edit_text(rapor, reply_markup=reply_markup)

    except Exception as e:
        log.exception("Analiz hatası")
        await bekle_msg.edit_text(f"❌ Hata oluştu: {str(e)}")


@dp.message(Command("temel"))
async def komut_temel(message: Message):
    """Temel analiz komutu."""
    if not await _rate_limit_check(message):
        return

    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Örnek: <code>/temel THYAO</code>")
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, tip = validate_symbol(girdi)

    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    log_query(message.from_user.id, message.from_user.username or "", sembol, "temel")
    bekle_msg = await message.reply(f"⏳ <b>{sembol}</b> temel analiz yapılıyor...")

    try:
        temel_v = await _async(temel_analiz_yap, sembol)

        if "Hata" in temel_v or not temel_v:
            await bekle_msg.edit_text(f"❌ Temel analiz verisi bulunamadı: <b>{sembol}</b>")
            return

        satirlar = [f"📊 <b>{sembol} Temel Analiz</b>\n"]
        for k, v in temel_v.items():
            if not k.startswith("_"):
                satirlar.append(f"• <b>{k}:</b> {v}")

        rapor = "\n".join(satirlar)
        # Telegram mesaj limiti: 4096 karakter
        if len(rapor) > 4000:
            rapor = rapor[:4000] + "\n...(devamı kısaltıldı)"

        await bekle_msg.edit_text(rapor, reply_markup=build_close_button())

    except Exception as e:
        log.exception("Temel analiz hatası")
        await bekle_msg.edit_text(f"❌ Hata oluştu: {str(e)}")


@dp.message(Command("teknik"))
async def komut_teknik(message: Message):
    """Teknik analiz komutu."""
    if not await _rate_limit_check(message):
        return

    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Örnek: <code>/teknik THYAO</code>")
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, tip = validate_symbol(girdi)

    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    log_query(message.from_user.id, message.from_user.username or "", sembol, "teknik")
    bekle_msg = await message.reply(f"⏳ <b>{sembol}</b> teknik analiz yapılıyor...")

    try:
        teknik_v = await _async(teknik_analiz_yap, sembol)

        if "Hata" in teknik_v or not teknik_v:
            await bekle_msg.edit_text(f"❌ Teknik analiz verisi bulunamadı: <b>{sembol}</b>")
            return

        satirlar = [f"📉 <b>{sembol} Teknik Analiz</b>\n"]
        for k, v in teknik_v.items():
            if not k.startswith("_"):
                satirlar.append(f"• <b>{k}:</b> {v}")

        rapor = "\n".join(satirlar)
        if len(rapor) > 4000:
            rapor = rapor[:4000] + "\n...(devamı kısaltıldı)"

        await bekle_msg.edit_text(rapor, reply_markup=build_close_button())

    except Exception as e:
        log.exception("Teknik analiz hatası")
        await bekle_msg.edit_text(f"❌ Hata oluştu: {str(e)}")


@dp.message(Command("grafik"))
async def komut_grafik(message: Message):
    """TradingView grafik komutu."""
    if not await _rate_limit_check(message):
        return

    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Örnek: <code>/grafik THYAO</code>")
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, tip = validate_symbol(girdi)

    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    log_query(message.from_user.id, message.from_user.username or "", sembol, "grafik")
    await message.answer(f"📊 <b>{sembol}</b> grafiği hazırlanıyor, lütfen bekleyin...")

    path = os.path.join(LOG_DIR, f"chart_{message.from_user.id}.png")
    success = await tv_grafik_cek(sembol, path)
    if success and os.path.exists(path):
        await message.answer_photo(
            FSInputFile(path),
            caption=f"📈 <b>{sembol}</b> TradingView Grafiği"
        )
    else:
        await message.answer(f"❌ <b>{sembol}</b> grafiği çekilemedi. Sembolü kontrol edin.")


@dp.message(Command("tahmin"))
async def komut_tahmin(message: Message):
    """AI fiyat tahmini komutu."""
    if not await _rate_limit_check(message):
        return

    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Örnek: <code>/tahmin THYAO</code>")
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, tip = validate_symbol(girdi)

    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    log_query(message.from_user.id, message.from_user.username or "", sembol, "tahmin")
    bekle_msg = await message.reply(f"🤖 <b>{sembol}</b> AI tahmini hazırlanıyor...")

    try:
        teknik_v = await _async(teknik_analiz_yap, sembol)
        tahmin = await ai_tahmin_yap(sembol, teknik_v)

        rapor = f"🔮 <b>{sembol} AI Fiyat Tahmini</b>\n\n{tahmin}"
        if len(rapor) > 4000:
            rapor = rapor[:4000] + "\n...(devamı kısaltıldı)"

        await bekle_msg.edit_text(rapor, reply_markup=build_close_button())

    except Exception as e:
        log.exception("Tahmin hatası")
        await bekle_msg.edit_text(f"❌ Hata oluştu: {str(e)}")


@dp.message(Command("trend"))
async def komut_trend(message: Message):
    """Popüler varlıklar komutu."""
    if not await _rate_limit_check(message):
        return

    bekle_msg = await message.reply("📈 Popüler varlıklar yükleniyor...")

    # Popüler semboller listesi
    populer = {
        "BIST": ["THYAO.IS", "ASELS.IS", "SASA.IS", "KCHOL.IS", "EREGL.IS"],
        "Kripto": ["BTC-USD", "ETH-USD", "BNB-USD"],
        "Global": ["AAPL", "MSFT", "TSLA", "NVDA"],
    }

    satirlar = ["📊 <b>Popüler Varlıklar</b>\n"]

    for kategori, semboller in populer.items():
        satirlar.append(f"\n<b>— {kategori} —</b>")
        for sembol in semboller[:3]:  # İlk 3'ü göster
            satirlar.append(f"• <code>/analiz {sembol.replace('.IS', '')}</code>")

    satirlar.append("\n💡 <i>Analiz için sembol koduna tıklayın.</i>")
    await bekle_msg.edit_text("\n".join(satirlar))


# ═══════════════════════════════════════════════════════════════
# UYARI KOMUTLARI
# ═══════════════════════════════════════════════════════════════

@dp.message(Command("uyari"))
async def komut_uyari(message: Message):
    """
    Fiyat veya RSI uyarısı kurar.
    Kullanım: /uyari SEMBOL TIP HEDEF
    Tipler: fiyat_ust, fiyat_alt, rsi_ust, rsi_alt
    Örnek: /uyari THYAO fiyat_ust 50
    """
    if not await _rate_limit_check(message):
        return

    parcalar = message.text.split()
    if len(parcalar) < 4:
        await message.reply(
            "⚠️ <b>Kullanım:</b> <code>/uyari SEMBOL TIP HEDEF</code>\n\n"
            "<b>Tipler:</b>\n"
            "• <code>fiyat_ust</code> — Fiyat bu değerin üzerine çıkınca\n"
            "• <code>fiyat_alt</code> — Fiyat bu değerin altına düşünce\n"
            "• <code>rsi_ust</code> — RSI bu değerin üzerine çıkınca\n"
            "• <code>rsi_alt</code> — RSI bu değerin altına düşünce\n\n"
            "<b>Örnek:</b> <code>/uyari THYAO fiyat_ust 50</code>"
        )
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, _ = validate_symbol(girdi)
    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    tip = parcalar[2].lower()
    gecerli_tipler = ["fiyat_ust", "fiyat_alt", "rsi_ust", "rsi_alt"]
    if tip not in gecerli_tipler:
        await message.reply(
            f"❌ Geçersiz uyarı tipi. Geçerli tipler: {', '.join(gecerli_tipler)}"
        )
        return

    hedef = validate_numeric(parcalar[3], min_val=0)
    if hedef is None:
        await message.reply("❌ Geçersiz hedef değer. Pozitif sayı giriniz.")
        return

    try:
        await uyari_ekle(message.from_user.id, sembol, tip, str(hedef))
        tip_aciklama = {
            "fiyat_ust": f"fiyat {hedef} üzerine çıkınca",
            "fiyat_alt": f"fiyat {hedef} altına düşünce",
            "rsi_ust": f"RSI {hedef} üzerine çıkınca",
            "rsi_alt": f"RSI {hedef} altına düşünce",
        }
        await message.reply(
            f"✅ <b>Uyarı kuruldu!</b>\n"
            f"📌 <b>{sembol}</b> {tip_aciklama[tip]} bildirim alacaksınız."
        )
    except Exception as e:
        log.exception("Uyarı ekleme hatası")
        await message.reply(f"❌ Uyarı kurulamadı: {str(e)}")


@dp.message(Command("uyarilarim"))
async def komut_uyarilarim(message: Message):
    """Kullanıcının aktif uyarılarını listeler."""
    uyarilar = await kullanici_uyarilari_getir(message.from_user.id)

    if not uyarilar:
        await message.reply(
            "📭 Aktif uyarınız yok.\n\n"
            "Uyarı kurmak için: <code>/uyari THYAO fiyat_ust 50</code>"
        )
        return

    satirlar = [f"🔔 <b>Aktif Uyarılarınız ({len(uyarilar)} adet)</b>\n"]
    for u in uyarilar:
        satirlar.append(
            f"• <b>#{u['id']}</b> {u['sembol']} — {u['tip']} @ {u['hedef_deger']}"
        )

    satirlar.append("\n<i>Uyarı silmek için: /uyari_sil ID</i>")
    await message.reply("\n".join(satirlar))


@dp.message(Command("uyari_sil"))
async def komut_uyari_sil(message: Message):
    """Uyarı siler."""
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Kullanım: <code>/uyari_sil ID</code>")
        return

    try:
        uyari_id = int(parcalar[1])
        await uyari_sil(uyari_id)
        await message.reply(f"✅ Uyarı #{uyari_id} silindi.")
    except ValueError:
        await message.reply("❌ Geçersiz uyarı ID.")
    except Exception as e:
        await message.reply(f"❌ Uyarı silinemedi: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# PORTFÖY KOMUTLARI
# ═══════════════════════════════════════════════════════════════

@dp.message(Command("portfoy"))
async def komut_portfoy(message: Message):
    """Portföy özeti komutu."""
    if not await _rate_limit_check(message):
        return

    bekle_msg = await message.reply("⏳ Portföy hesaplanıyor...")
    try:
        ozet = await portfoy_ozeti_hazirla(message.from_user.id)
        await bekle_msg.edit_text(ozet, reply_markup=build_close_button())
    except Exception as e:
        log.exception("Portföy hatası")
        await bekle_msg.edit_text(f"❌ Portföy yüklenemedi: {str(e)}")


@dp.message(Command("portfoy_ekle"))
async def komut_portfoy_ekle(message: Message):
    """
    Portföye varlık ekler.
    Kullanım: /portfoy_ekle SEMBOL MIKTAR MALIYET
    Örnek: /portfoy_ekle THYAO 100 45.50
    """
    parcalar = message.text.split()
    if len(parcalar) < 4:
        await message.reply(
            "⚠️ <b>Kullanım:</b> <code>/portfoy_ekle SEMBOL MIKTAR MALIYET</code>\n\n"
            "<b>Örnek:</b> <code>/portfoy_ekle THYAO 100 45.50</code>"
        )
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, _ = validate_symbol(girdi)
    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    sonuc = await portfoy_varlik_ekle(
        message.from_user.id, sembol, parcalar[2], parcalar[3]
    )
    await message.reply(sonuc)


@dp.message(Command("portfoy_sil"))
async def komut_portfoy_sil(message: Message):
    """Portföyden varlık siler."""
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Kullanım: <code>/portfoy_sil SEMBOL</code>")
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, _ = validate_symbol(girdi)
    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    sonuc = await portfoy_varlik_sil(message.from_user.id, sembol)
    await message.reply(sonuc)


# ═══════════════════════════════════════════════════════════════
# FAVORİ KOMUTLARI
# ═══════════════════════════════════════════════════════════════

@dp.message(Command("favoriler"))
async def komut_favoriler(message: Message):
    """Favori listesi komutu."""
    favoriler = await favorileri_getir(message.from_user.id)

    if not favoriler:
        await message.reply(
            "⭐ Favori listeniz boş.\n\n"
            "Eklemek için: <code>/favori_ekle THYAO</code>"
        )
        return

    satirlar = [f"⭐ <b>Favori Listeniz ({len(favoriler)} sembol)</b>\n"]
    for sembol in favoriler:
        satirlar.append(f"• <code>/analiz {sembol.replace('.IS', '')}</code>")

    await message.reply("\n".join(satirlar))


@dp.message(Command("favori_ekle"))
async def komut_favori_ekle(message: Message):
    """Favorilere sembol ekler."""
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Kullanım: <code>/favori_ekle SEMBOL</code>")
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, _ = validate_symbol(girdi)
    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    await favori_ekle(message.from_user.id, sembol)
    await message.reply(f"⭐ <b>{sembol}</b> favorilere eklendi.")


@dp.message(Command("favori_sil"))
async def komut_favori_sil(message: Message):
    """Favorilerden sembol siler."""
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply("⚠️ Kullanım: <code>/favori_sil SEMBOL</code>")
        return

    girdi = sanitize_text(parcalar[1])
    valid, sembol, _ = validate_symbol(girdi)
    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    await favori_sil(message.from_user.id, sembol)
    await message.reply(f"🗑️ <b>{sembol}</b> favorilerden çıkarıldı.")


# ═══════════════════════════════════════════════════════════════
# CALLBACK HANDLER'LAR (Inline Menü)
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "close")
async def callback_kapat(callback: CallbackQuery):
    """Mesajı kapatır."""
    await callback.message.delete()
    await callback.answer()


@dp.callback_query(F.data.startswith("analiz:temel:"))
async def callback_temel(callback: CallbackQuery):
    """Temel analiz callback."""
    sembol = callback.data.split(":")[2]
    await callback.answer("⏳ Temel analiz yükleniyor...")

    try:
        temel_v = await _async(temel_analiz_yap, sembol)

        if "Hata" in temel_v or not temel_v:
            await callback.message.edit_text(
                f"❌ Temel analiz verisi bulunamadı: <b>{sembol}</b>",
                reply_markup=build_close_button()
            )
            return

        satirlar = [f"📊 <b>{sembol} Temel Analiz</b>\n"]
        for k, v in temel_v.items():
            if not k.startswith("_"):
                satirlar.append(f"• <b>{k}:</b> {v}")

        rapor = "\n".join(satirlar)
        if len(rapor) > 4000:
            rapor = rapor[:4000] + "\n...(devamı kısaltıldı)"

        await callback.message.edit_text(rapor, reply_markup=build_close_button())

    except Exception as e:
        log.exception("Callback temel analiz hatası")
        await callback.message.edit_text(f"❌ Hata: {str(e)}", reply_markup=build_close_button())


@dp.callback_query(F.data.startswith("analiz:teknik:"))
async def callback_teknik(callback: CallbackQuery):
    """Teknik analiz callback."""
    sembol = callback.data.split(":")[2]
    await callback.answer("⏳ Teknik analiz yükleniyor...")

    try:
        teknik_v = await _async(teknik_analiz_yap, sembol)

        if "Hata" in teknik_v or not teknik_v:
            await callback.message.edit_text(
                f"❌ Teknik analiz verisi bulunamadı: <b>{sembol}</b>",
                reply_markup=build_close_button()
            )
            return

        satirlar = [f"📉 <b>{sembol} Teknik Analiz</b>\n"]
        for k, v in teknik_v.items():
            if not k.startswith("_"):
                satirlar.append(f"• <b>{k}:</b> {v}")

        rapor = "\n".join(satirlar)
        if len(rapor) > 4000:
            rapor = rapor[:4000] + "\n...(devamı kısaltıldı)"

        await callback.message.edit_text(rapor, reply_markup=build_close_button())

    except Exception as e:
        log.exception("Callback teknik analiz hatası")
        await callback.message.edit_text(f"❌ Hata: {str(e)}", reply_markup=build_close_button())


@dp.callback_query(F.data.startswith("analiz:ai:"))
async def callback_ai(callback: CallbackQuery):
    """AI yorum callback."""
    sembol = callback.data.split(":")[2]
    await callback.answer("🤖 AI analiz hazırlanıyor...")

    try:
        temel_v, teknik_v = await asyncio.gather(
            _async(temel_analiz_yap, sembol),
            _async(teknik_analiz_yap, sembol)
        )
        yorum = await ai_analist_yorumu(sembol, temel_v, teknik_v)

        rapor = f"🤖 <b>{sembol} AI Analiz Yorumu</b>\n\n{yorum}"
        if len(rapor) > 4000:
            rapor = rapor[:4000] + "\n...(devamı kısaltıldı)"

        await callback.message.edit_text(rapor, reply_markup=build_close_button())

    except Exception as e:
        log.exception("Callback AI analiz hatası")
        await callback.message.edit_text(f"❌ Hata: {str(e)}", reply_markup=build_close_button())


@dp.callback_query(F.data.startswith("grafik:"))
async def callback_grafik(callback: CallbackQuery):
    """Grafik callback."""
    sembol = callback.data.split(":")[1]
    await callback.answer("📊 Grafik hazırlanıyor...")

    path = os.path.join(LOG_DIR, f"chart_{callback.from_user.id}.png")
    success = await tv_grafik_cek(sembol, path)

    if success and os.path.exists(path):
        await callback.message.answer_photo(
            FSInputFile(path),
            caption=f"📈 <b>{sembol}</b> TradingView Grafiği"
        )
    else:
        await callback.message.answer(
            f"❌ <b>{sembol}</b> grafiği çekilemedi."
        )


@dp.callback_query(F.data.startswith("favori:toggle:"))
async def callback_favori_toggle(callback: CallbackQuery):
    """Favori ekle/çıkar callback."""
    sembol = callback.data.split(":")[2]
    eklendi = await favori_toggle(callback.from_user.id, sembol)

    if eklendi:
        await callback.answer(f"⭐ {sembol} favorilere eklendi!")
    else:
        await callback.answer(f"🗑️ {sembol} favorilerden çıkarıldı.")


# ═══════════════════════════════════════════════════════════════
# GENEL MESAJ HANDLER (AI Asistan)
# ═══════════════════════════════════════════════════════════════

@dp.message(F.text & ~F.text.startswith("/"))
async def genel_mesaj(message: Message):
    """Komut olmayan mesajları AI asistana yönlendirir."""
    if not await _rate_limit_check(message):
        return

    # Kısa mesajları filtrele
    if len(message.text.strip()) < 3:
        return

    bekle_msg = await message.reply("🤖 Düşünüyorum...")

    try:
        yanit = await ai_nlp_sorgu(message.text)
        if len(yanit) > 4000:
            yanit = yanit[:4000] + "\n...(devamı kısaltıldı)"
        await bekle_msg.edit_text(yanit)
    except Exception as e:
        log.exception("AI asistan hatası")
        await bekle_msg.edit_text(
            "❌ Şu an yanıt veremiyorum. Lütfen daha sonra tekrar deneyin."
        )


# ═══════════════════════════════════════════════════════════════
# ANA DÖNGÜ
# ═══════════════════════════════════════════════════════════════

async def main():
    """Bot ana döngüsü."""
    try:
        validate_startup()
    except Exception as e:
        log.critical(f"❌ Başlatma hatası: {e}")
        return

    # Cache temizliği
    baslangic_temizligi()

    # Audit logging
    setup_audit_logging()

    # Veritabanı başlatma
    await db_init()

    # Monitoring (Health Check)
    try:
        from monitoring.health_check import start_health_server
        asyncio.create_task(start_health_server(
            host=settings.HEALTH_HOST,
            port=settings.HEALTH_PORT,
            bot=bot
        ))
        log.info(f"🔍 Health server: http://{settings.HEALTH_HOST}:{settings.HEALTH_PORT}/health")
    except Exception as e:
        log.error(f"Health server başlatılamadı: {e}")

    # Arka Plan Görevleri
    asyncio.create_task(uyari_kontrol_dongusu(bot))

    # Sinyal Yakalayıcılar
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda s=sig: asyncio.create_task(shutdown(loop, s))
        )

    log.info("🚀 Finans Botu başlatıldı!")
    log.info(settings.startup_log())

    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
