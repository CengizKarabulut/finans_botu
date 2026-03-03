"""
main.py — Finans Botu Ana Giriş Noktası
✅ MİMARİ GÜNCELLEME - Zeki Sembol Doğrulama ve Advanced Graceful Shutdown.
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
from prometheus_client import start_http_server

# ═══════════════════════════════════════════════════════════════
# IMPORTLAR
# ═══════════════════════════════════════════════════════════════
from config import settings, validate_startup
from security.input_validator import validate_symbol, sanitize_text
from ux.inline_menus import build_analiz_menu, build_close_button

from temel_analiz   import temel_analiz_yap
from teknik_analiz  import teknik_analiz_yap
from analist_motoru import ai_analist_yorumu, ai_nlp_sorgu
from db import db_init, kullanici_kaydet, close_db
from alert_motoru import uyari_kontrol_dongusu
from tradingview_motoru import tv_grafik_cek, TVBrowser

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(os.path.join(LOG_DIR, "bot.log"), maxBytes=10*1024*1024, backupCount=5)
    ]
)
log = logging.getLogger("finans_botu")

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
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))

# ═══════════════════════════════════════════════════════════════
# KOMUTLAR
# ═══════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def komut_start(message: Message):
    await kullanici_kaydet(message.from_user.id, message.from_user.username or "")
    welcome = (
        f"🚀 <b>Finans Botu’na Hoş Geldiniz!</b>\n\n"
        f"Hisse senedi, kripto ve döviz analizleri için emrinizdeyim.\n\n"
        f"📌 <b>Temel Komutlar:</b>\n"
        f"• <code>/analiz THYAO</code> - Kapsamlı analiz\n"
        f"• <code>/grafik BTCUSD</code> - TradingView grafiği\n"
        f"• <code>/tahmin AAPL</code> - AI fiyat tahmini\n"
        f"• <code>/trend</code> - Popüler varlıklar\n"
        f"• <code>/favoriler</code> - Favori listeniz\n\n"
        f"💡 Herhangi bir şey yazarak AI asistanımla sohbet edebilirsiniz."
    )
    await message.reply(welcome)

@dp.message(Command("analiz"))
async def komut_analiz(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: <code>/analiz THYAO</code>")
        return
    
    girdi = sanitize_text(parcalar[1])
    valid, sembol, tip = validate_symbol(girdi)
    
    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    bekle_msg = await message.reply(f"⏳ <b>{sembol}</b> ({tip}) verileri işleniyor...")
    
    try:
        temel_v, teknik_v = await asyncio.gather(
            _async(temel_analiz_yap, sembol),
            _async(teknik_analiz_yap, sembol)
        )
        
        if ("Hata" in temel_v or not temel_v) and ("Hata" in teknik_v or not teknik_v):
            await bekle_msg.edit_text(f"❌ Veri bulunamadı: {sembol}")
            return

        fiyat = temel_v.get("Fiyat", teknik_v.get("Fiyat", "—"))
        degisim = temel_v.get("Günlük Değişim (%)", "—")
        
        rapor = (
            f"📊 <b>{sembol} Analiz Özeti</b>\n"
            f"💰 Fiyat: <b>{fiyat}</b>\n"
            f"📈 Değişim: <b>{degisim}</b>\n\n"
            f"Detaylı analiz için aşağıdaki butonları kullanabilirsiniz."
        )
        
        reply_markup = build_analiz_menu(sembol)
        await bekle_msg.edit_text(rapor, reply_markup=reply_markup)
        
    except Exception as e:
        log.exception("Analiz hatası")
        await bekle_msg.edit_text(f"❌ Hata oluştu: {e}")

@dp.message(Command("grafik"))
async def komut_grafik(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: <code>/grafik THYAO</code>")
        return
    
    girdi = sanitize_text(parcalar[1])
    valid, sembol, tip = validate_symbol(girdi)
    
    if not valid:
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    await message.answer(f"📊 <b>{sembol}</b> grafiği hazırlanıyor, lütfen bekleyin...")
    
    path = f"logs/chart_{message.from_user.id}.png"
    success = await tv_grafik_cek(sembol, path)
    if success:
        await message.answer_photo(FSInputFile(path), caption=f"📈 {sembol} TradingView Grafiği")
    else:
        await message.answer(f"❌ {sembol} grafiği çekilemedi. Sembolü kontrol edin.")

# ═══════════════════════════════════════════════════════════════
# ANA DÖNGÜ
# ═══════════════════════════════════════════════════════════════

async def main():
    try:
        validate_startup()
    except Exception as e:
        log.critical(f"❌ Başlatma hatası: {e}")
        return

    await db_init()
    
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher()

    # Monitoring (Prometheus)
    try:
        start_http_server(settings.HEALTH_PORT)
        log.info(f"🔍 Monitoring server: http://localhost:{settings.HEALTH_PORT}/metrics")
    except Exception as e:
        log.error(f"Monitoring server başlatılamadı: {e}")

    # Arka Plan Görevleri
    asyncio.create_task(uyari_kontrol_dongusu(bot))
    
    # Sinyal Yakalayıcılar
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(loop, s)))

    log.info("🚀 Finans Botu başlatıldı!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
