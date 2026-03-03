"""
Finans Botu — aiogram 3.x + asyncio + SQLite
Tüm sync modüller (temel_analiz, teknik_analiz, vb.) run_in_executor ile çağrılır.
✅ PROFESYONEL VERSİYON - Callback fix, AI fallback, TradingView fix.
"""
import os
import re
import asyncio
import logging
from datetime import datetime
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
from monitoring import setup_structured_logging, start_health_server, inc_counter
from security import setup_audit_logging, log_user_action, log_security_event
from security.input_validator import validate_symbol, sanitize_text
from security.rate_limiter import check_rate_limit
from ux.user_prefs import ensure_prefs_table
from ux.inline_menus import build_analiz_menu, build_close_button

from temel_analiz   import temel_analiz_yap
from teknik_analiz  import teknik_analiz_yap
from analist_motoru import ai_analist_yorumu, ai_piyasa_yorumu, ai_tahmin_yap, ai_nlp_sorgu
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

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)

logging.basicConfig(
    level=logging.INFO,
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
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN tanımlı değil.")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()

_son_istek: dict = {}
TELEGRAM_LIMIT = 4000

# ═══════════════════════════════════════════════════════════════
# YARDIMCILAR
# ═══════════════════════════════════════════════════════════════
def h(text) -> str: return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def bold(text) -> str: return f"<b>{h(text)}</b>"
def code(text) -> str: return f"<code>{h(text)}</code>"

async def _async(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))

def rate_limit_kontrol(user_id: int) -> int:
    now = datetime.now()
    if user_id in _son_istek:
        fark = (now - _son_istek[user_id]).total_seconds()
        if fark < 5: return int(5 - fark)
    return 0

async def _gonder(chat_id, mesaj_id, metin, duzenle=False, reply_markup=None):
    try:
        if duzenle:
            await bot.edit_message_text(metin, chat_id, mesaj_id, reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id, metin, reply_markup=reply_markup)
    except Exception as e:
        log.error(f"Mesaj gönderilemedi: {e}")
        await bot.send_message(chat_id, metin, reply_markup=reply_markup)

def _normalize_ticker(ticker: str) -> str:
    t = ticker.upper().strip()
    if t.isalpha() and len(t) <= 5: # ABD hissesi varsayalım
        return t
    if "." not in t and len(t) >= 4: # BIST hissesi varsayalım
        return t + ".IS"
    return t

# ═══════════════════════════════════════════════════════════════
# KOMUTLAR
# ═══════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def komut_start(message: Message):
    await kullanici_kaydet(message.from_user.id, message.from_user.username or "")
    welcome = (
        f"🚀 {bold('Finans Botu’na Hoş Geldiniz!')}\n\n"
        f"Hisse senedi, kripto ve döviz analizleri için emrinizdeyim.\n\n"
        f"📌 {bold('Temel Komutlar:')}\n"
        f"• {code('/analiz THYAO')} - Kapsamlı analiz\n"
        f"• {code('/grafik BTCUSD')} - TradingView grafiği\n"
        f"• {code('/tahmin AAPL')} - AI fiyat tahmini\n"
        f"• {code('/trend')} - Popüler varlıklar\n"
        f"• {code('/favoriler')} - Favori listeniz\n\n"
        f"💡 Herhangi bir şey yazarak AI asistanımla sohbet edebilirsiniz."
    )
    await message.reply(welcome)

@dp.message(Command("analiz", "temel", "teknik", "ai"))
async def komut_analiz(message: Message):
    komut = message.text.split()[0][1:].lower()
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: {code('/' + komut + ' THYAO')}")
        return
    
    girdi = parcalar[1].upper().strip()
    user_id = message.from_user.id
    
    bekleme = rate_limit_kontrol(user_id)
    if bekleme > 0:
        await message.reply(f"⏳ {bekleme} saniye bekleyin.")
        return
    
    _son_istek[user_id] = datetime.now()
    hisse_kodu = _normalize_ticker(girdi)
    
    bekle_msg = await message.reply(f"⏳ {bold(hisse_kodu)} verileri işleniyor...")
    asyncio.create_task(_analiz_isle(message.chat.id, bekle_msg.message_id, hisse_kodu, komut))

@dp.message(Command("grafik"))
async def komut_grafik(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: {code('/grafik THYAO')}")
        return
    
    sembol = parcalar[1].upper().strip()
    await message.answer(f"📊 {bold(sembol)} grafiği hazırlanıyor, lütfen bekleyin...")
    
    path = f"logs/chart_{message.from_user.id}.png"
    success = await tv_grafik_cek(sembol, path)
    if success:
        await message.answer_photo(FSInputFile(path), caption=f"📈 {sembol} TradingView Grafiği")
    else:
        await message.answer(f"❌ {sembol} grafiği çekilemedi. Sembolü kontrol edin.")

@dp.message(Command("tahmin"))
async def komut_tahmin(message: Message):
    parcalar = message.text.split()
    if len(parcalar) < 2:
        await message.reply(f"⚠️ Örnek: {code('/tahmin BTCUSD')}")
        return
    
    sembol = parcalar[1].upper().strip()
    await message.answer(f"🤖 {bold(sembol)} için AI tahmini hazırlanıyor...")
    
    teknik = await _async(teknik_analiz_yap, sembol)
    tahmin = await _async(ai_tahmin_yap, sembol, teknik)
    await message.answer(f"🔮 {bold(sembol + ' AI Tahmini')}\n\n{tahmin}")

# ═══════════════════════════════════════════════════════════════
# ASYNC İŞLEMLER
# ═══════════════════════════════════════════════════════════════

async def _analiz_isle(chat_id: int, mesaj_id: int, hisse_kodu: str, komut: str):
    try:
        # Verileri çek
        temel_v, teknik_v = await asyncio.gather(
            _async(temel_analiz_yap, hisse_kodu),
            _async(teknik_analiz_yap, hisse_kodu)
        )
        
        if "Hata" in temel_v and "Hata" in teknik_v:
            await _gonder(chat_id, mesaj_id, f"❌ Veri bulunamadı: {hisse_kodu}", duzenle=True)
            return

        # Rapor oluştur (Basitleştirilmiş özet)
        fiyat = temel_v.get("Fiyat", teknik_v.get("Fiyat", "—"))
        degisim = temel_v.get("Günlük Değişim (%)", "—")
        
        rapor = (
            f"📊 {bold(hisse_kodu + ' Analiz Özeti')}\n"
            f"💰 Fiyat: {bold(str(fiyat))}\n"
            f"📈 Değişim: {bold(str(degisim))}\n\n"
            f"Detaylı analiz için aşağıdaki butonları kullanabilirsiniz."
        )
        
        reply_markup = build_analiz_menu(hisse_kodu)
        await _gonder(chat_id, mesaj_id, rapor, duzenle=True, reply_markup=reply_markup)
        
    except Exception as e:
        log.exception("Analiz hatası")
        await _gonder(chat_id, mesaj_id, f"❌ Hata oluştu: {e}", duzenle=True)

# ═══════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("analiz:"))
async def callback_analiz(callback: CallbackQuery):
    _, tip, sembol = callback.data.split(":")
    await callback.answer(f"{sembol} {tip} analizi hazırlanıyor...")
    
    if tip == "ai":
        bekle = await callback.message.answer(f"🤖 {bold(sembol)} AI yorumu hazırlanıyor...")
        temel = await _async(temel_analiz_yap, sembol)
        teknik = await _async(teknik_analiz_yap, sembol)
        yorum = await _async(ai_analist_yorumu, sembol, temel, teknik)
        await bekle.edit_text(f"🤖 {bold(sembol + ' AI Analizi')}\n\n{yorum}")
    elif tip == "teknik":
        teknik = await _async(teknik_analiz_yap, sembol)
        # Teknik rapor formatla ve gönder...
        await callback.message.answer(f"📉 {bold(sembol)} Teknik Veriler:\n{str(teknik)[:500]}...")
    elif tip == "temel":
        temel = await _async(temel_analiz_yap, sembol)
        await callback.message.answer(f"📊 {bold(sembol)} Temel Veriler:\n{str(temel)[:500]}...")

@dp.callback_query(F.data.startswith("grafik:"))
async def callback_grafik_btn(callback: CallbackQuery):
    sembol = callback.data.split(":")[1]
    await callback.answer(f"{sembol} grafiği çekiliyor...")
    path = f"logs/chart_{callback.from_user.id}.png"
    if await tv_grafik_cek(sembol, path):
        await callback.message.answer_photo(FSInputFile(path), caption=f"📈 {sembol} Grafiği")
    else:
        await callback.message.answer("❌ Grafik hatası.")

@dp.callback_query(F.data == "close")
async def callback_close(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()

# ═══════════════════════════════════════════════════════════════
# NLP & STARTUP
# ═══════════════════════════════════════════════════════════════

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_nlp(message: Message):
    await kullanici_kaydet(message.from_user.id, message.from_user.username or "")
    yanit = await _async(ai_nlp_sorgu, message.text)
    await message.answer(yanit)

async def main():
    validate_startup()
    await db_init()
    await ensure_prefs_table()
    baslangic_temizligi()
    
    asyncio.create_task(uyari_kontrol_dongusu(bot))
    log.info("🚀 Bot başlatıldı.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
