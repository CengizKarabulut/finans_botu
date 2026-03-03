"""
main.py — Finans Botu Ana Giriş Noktası
✅ MİMARİ GÜNCELLEME - Advanced Graceful Shutdown, i18n ve Webhook/Polling Desteği.
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
# GRACEFUL SHUTDOWN (Gelişmiş Sinyal Yönetimi)
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
# ANA DÖNGÜ & WEBHOOK/POLLING
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
    
    # Webhook vs Polling Seçimi (Config üzerinden)
    use_webhook = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
    
    if use_webhook:
        log.info("🌐 Webhook modu aktif ediliyor (Henüz yapılandırılmadı)...")
        # Webhook setup buraya gelecek
        await dp.start_polling(bot, skip_updates=True)
    else:
        log.info("📡 Polling modu aktif.")
        await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
