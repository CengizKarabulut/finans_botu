"""
alert_motoru.py — Fiyat ve RSI uyarılarını arka planda kontrol eder.
✅ MİMARİ GÜNCELLEME - Sembol Gruplama (API Optimizasyonu) ve Robust Parsing.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from decimal import Decimal
from collections import defaultdict

from db import uyarilari_getir, uyari_sil
from veri_motoru import get_fiyat_hiyerarsik
from teknik_analiz import teknik_analiz_yap

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════

def _parse_decimal(val: Any) -> Optional[Decimal]:
    if val is None: return None
    try:
        if isinstance(val, str):
            temiz = ''.join(c for c in val if c.isdigit() or c in '.,-')
            if ',' in temiz and '.' in temiz:
                if temiz.find('.') < temiz.find(','):
                    temiz = temiz.replace('.', '').replace(',', '.')
                else:
                    temiz = temiz.replace(',', '')
            elif ',' in temiz:
                temiz = temiz.replace(',', '.')
            return Decimal(temiz) if temiz else None
        return Decimal(str(val))
    except Exception as e:
        log.debug(f"Decimal parse hatası ('{val}'): {e}")
        return None

async def _async_call(fn, *args, **kwargs) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

# ═══════════════════════════════════════════════════════════════════
# UYARI KONTROL DÖNGÜSÜ — ✅ SEMBOL GRUPLAMA (API OPTİMİZASYONU)
# ═══════════════════════════════════════════════════════════════════

async def uyari_kontrol_dongusu(bot):
    log.info("🔔 Uyarı kontrol döngüsü başlatıldı.")
    
    while True:
        try:
            uyarilar = await uyarilari_getir()
            if not uyarilar:
                await asyncio.sleep(60)
                continue

            # ✅ PERFORMANS: Sembolleri grupla (100 uyarı için 100 API çağrısı yerine 1 çağrı)
            sembol_gruplari = defaultdict(list)
            for uyari in uyarilar:
                sembol_gruplari[uyari['sembol']].append(uyari)

            for sembol, uyarilar_list in sembol_gruplari.items():
                try:
                    # 1. Fiyat Verisini Tek Seferde Çek
                    fiyat_verisi = await get_fiyat_hiyerarsik(sembol)
                    mevcut_fiyat = _parse_decimal(fiyat_verisi.get("fiyat"))
                    
                    # 2. Teknik Veriyi Tek Seferde Çek (Eğer RSI uyarısı varsa)
                    mevcut_rsi = None
                    if any(u['tip'].startswith('rsi') for u in uyarilar_list):
                        teknik = await _async_call(teknik_analiz_yap, sembol)
                        mevcut_rsi = _parse_decimal(teknik.get('RSI (14)'))

                    # 3. Tüm Uyarıları Bu Verilerle Kontrol Et
                    for uyari in uyarilar_list:
                        await _uyari_kontrol_et(bot, uyari, mevcut_fiyat, mevcut_rsi)
                    
                    # API limitlerini korumak için semboller arası kısa bekleme
                    await asyncio.sleep(1)
                except Exception as e:
                    log.error(f"Sembol işleme hatası ({sembol}): {e}")

            await asyncio.sleep(300) # 5 dakika
            
        except asyncio.CancelledError:
            log.info("🛑 Uyarı kontrol döngüsü iptal edildi.")
            break
        except Exception as e:
            log.exception(f"💥 Uyarı döngüsünde beklenmedik hata: {e}")
            await asyncio.sleep(60)

async def _uyari_kontrol_et(bot, uyari: Dict[str, Any], mevcut_fiyat: Decimal, mevcut_rsi: Decimal):
    sembol = uyari['sembol']
    user_id = uyari['user_id']
    tip = uyari['tip']
    hedef = _parse_decimal(uyari['hedef_deger'])
    uyari_id = uyari['id']

    if hedef is None: return

    tetiklendi = False
    mesaj = ""

    # Fiyat Kontrolü
    if tip.startswith('fiyat') and mevcut_fiyat is not None:
        if tip == 'fiyat_ust' and mevcut_fiyat >= hedef:
            tetiklendi = True
            mesaj = f"🚀 <b>Fiyat Uyarısı!</b>\n{sembol} fiyatı {hedef} üzerine çıktı.\nGüncel: {mevcut_fiyat:.2f}"
        elif tip == 'fiyat_alt' and mevcut_fiyat <= hedef:
            tetiklendi = True
            mesaj = f"⚠️ <b>Fiyat Uyarısı!</b>\n{sembol} fiyatı {hedef} altına düştü.\nGüncel: {mevcut_fiyat:.2f}"

    # RSI Kontrolü
    elif tip.startswith('rsi') and mevcut_rsi is not None:
        if tip == 'rsi_ust' and mevcut_rsi >= hedef:
            tetiklendi = True
            mesaj = f"📈 <b>RSI Uyarısı!</b>\n{sembol} RSI değeri {hedef} üzerine çıktı.\nGüncel RSI: {mevcut_rsi:.2f}"
        elif tip == 'rsi_alt' and mevcut_rsi <= hedef:
            tetiklendi = True
            mesaj = f"📉 <b>RSI Uyarısı!</b>\n{sembol} RSI değeri {hedef} altına düştü.\nGüncel RSI: {mevcut_rsi:.2f}"

    if tetiklendi and mesaj:
        try:
            await bot.send_message(user_id, mesaj, parse_mode="HTML")
            await uyari_sil(uyari_id)
            log.info(f"✅ Uyarı tetiklendi: {sembol} (ID: {uyari_id})")
        except Exception as e:
            log.error(f"Mesaj gönderilemedi (User: {user_id}): {e}")
