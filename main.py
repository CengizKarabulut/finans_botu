"""
main.py — Finans Botu Ana Giriş Noktası
✅ MİMARİ GÜNCELLEME - Graceful Shutdown, Prometheus Metrics ve Pydantic Settings.
"""
import os
import re
import asyncio
import logging
import signal
import sys
from datetime import datetime
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
from analist_motoru import ai_analist_yorumu, ai_piyasa_yorumu, ai_tahmin_yap, ai_nlp_sorgu
from cache_yonetici import baslangic_temizligi
from db import (
    db_init, favori_ekle, favori_sil, favorileri_getir, kullanici_kaydet,
    uyari_ekle, uyarilari_getir, uyari_sil,
    portfoy_guncelle, portfoy_getir, portfoy_sil, close_db
)
from alert_motoru import uyari_kontrol_dongusu
from tradingview_motoru import tv_grafik_cek, TVBrowser

# ═══════════════════════════════════════════════════════════════
# LOGGING (Structured & Rotating)
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
# BOT & DISPATCHER
# ═══════════════════════════════════════════════════════════════
bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()

# ═══════════════════════════════════════════════════════════════
# YARDIMCILAR — ✅ ZEKİ SEMBOL NORMALİZASYONU
# ═══════════════════════════════════════════════════════════════

def _normalize_ticker(ticker: str) -> str:
    """Sembolü zeki bir şekilde normalize eder."""
    t = ticker.upper().strip()
    if t.endswith(".IS") or "-" in t or "=" in t:
        return t
    kripto_ciftleri = ["USD", "TRY", "USDT", "EUR"]
    for cift in kripto_ciftleri:
        if t.endswith(cift) and len(t) > len(cift):
            base = t[:-len(cift)]
            return f"{base}-{cift}"
    if t.isalpha() and 4 <= len(t) <= 5:
        return f"{t}.IS"
    return t

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
    if not validate_symbol(girdi):
        await message.reply("❌ Geçersiz sembol formatı.")
        return

    hisse_kodu = _normalize_ticker(girdi)
    bekle_msg = await message.reply(f"⏳ <b>{hisse_kodu}</b> verileri işleniyor...")
    
    try:
        temel_v, teknik_v = await asyncio.gather(
            _async(temel_analiz_yap, hisse_kodu),
            _async(teknik_analiz_yap, hisse_kodu)
        )
        
        if ("Hata" in temel_v or not temel_v) and ("Hata" in teknik_v or not teknik_v):
            await bekle_msg.edit_text(f"❌ Veri bulunamadı: {hisse_kodu}")
            return

        fiyat = temel_v.get("Fiyat", teknik_v.get("Fiyat", "—"))
        degisim = temel_v.get("Günlük Değişim (%)", "—")
        
        rapor = (
            f"📊 <b>{hisse_kodu} Analiz Özeti</b>\n"
            f"💰 Fiyat: <b>{fiyat}</b>\n"
            f"📈 Değişim: <b>{degisim}</b>\n\n"
            f"Detaylı analiz için aşağıdaki butonları kullanabilirsiniz."
        )
        
        reply_markup = build_analiz_menu(hisse_kodu)
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
    
    sembol = _normalize_ticker(sanitize_text(parcalar[1]))
    await message.answer(f"📊 <b>{sembol}</b> grafiği hazırlanıyor, lütfen bekleyin...")
    
    path = f"logs/chart_{message.from_user.id}.png"
    success = await tv_grafik_cek(sembol, path)
    if success:
        await message.answer_photo(FSInputFile(path), caption=f"📈 {sembol} TradingView Grafiği")
    else:
        await message.answer(f"❌ {sembol} grafiği çekilemedi. Sembolü kontrol edin.")

# ═══════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("analiz:"))
async def callback_analiz(callback: CallbackQuery):
    _, tip, sembol = callback.data.split(":")
    await callback.answer(f"{sembol} {tip} analizi hazırlanıyor...")
    
    if tip == "ai":
        bekle = await callback.message.answer(f"🤖 <b>{sembol}</b> AI yorumu hazırlanıyor...")
        temel = await _async(temel_analiz_yap, sembol)
        teknik = await _async(teknik_analiz_yap, sembol)
        yorum = await ai_analist_yorumu(sembol, temel, teknik)
        await bekle.edit_text(f"🤖 <b>{sembol} AI Analizi</b>\n\n{yorum}")
    elif tip == "teknik":
        teknik = await _async(teknik_analiz_yap, sembol)
        res = f"📉 <b>{sembol} Teknik Veriler</b>\n\n"
        for k, v in teknik.items():
            if not k.startswith("_") and "SMA" not in k and "EMA" not in k:
                res += f"• {k}: {v}\n"
        await callback.message.answer(res[:4000])
    elif tip == "temel":
        temel = await _async(temel_analiz_yap, sembol)
        res = f"📊 <b>{sembol} Temel Veriler</b>\n\n"
        for k, v in temel.items():
            if not k.startswith("_"):
                res += f"• {k}: {v}\n"
        await callback.message.answer(res[:4000])

@dp.callback_query(F.data == "close")
async def callback_close(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()

# ═══════════════════════════════════════════════════════════════
# NLP & SHUTDOWN
# ═══════════════════════════════════════════════════════════════

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_nlp(message: Message):
    await kullanici_kaydet(message.from_user.id, message.from_user.username or "")
    yanit = await ai_nlp_sorgu(message.text)
    await message.answer(yanit)

async def shutdown(bot: Bot, dp: Dispatcher):
    """Botu ve kaynakları temiz bir şekilde kapatır."""
    log.info("🛑 Bot kapatılıyor, kaynaklar temizleniyor...")
    await dp.stop_polling()
    await close_db()
    await TVBrowser.close()
    await bot.session.close()
    log.info("✅ Bot başarıyla kapatıldı.")
    sys.exit(0)

async def main():
    try:
        validate_startup()
    except Exception as e:
        log.critical(f"❌ Başlatma hatası: {e}")
        return

    await db_init()
    baslangic_temizligi()
    
    # Monitoring (Prometheus)
    try:
        start_http_server(settings.HEALTH_PORT)
        log.info(f"🔍 Monitoring server: http://localhost:{settings.HEALTH_PORT}/metrics")
    except Exception as e:
        log.error(f"Monitoring server başlatılamadı: {e}")

    asyncio.create_task(uyari_kontrol_dongusu(bot))
    
    # Graceful Shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(bot, dp)))

    log.info("🚀 Finans Botu başlatıldı!")
    try:
        await dp.start_polling(bot)
    finally:
        await shutdown(bot, dp)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
