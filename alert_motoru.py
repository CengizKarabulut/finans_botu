"""
alert_motoru.py — Fiyat ve RSI uyarılarını arka planda kontrol eder.
✅ MİMARİ GÜNCELLEME - Hiyerarşik veri çekme, async-safe döngü ve Decimal hassasiyeti.
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any, List
from decimal import Decimal

from db import uyarilari_getir, uyari_sil
from veri_motoru import get_fiyat_hiyerarsik
from teknik_analiz import teknik_analiz_yap

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR — ✅ ROBUST PARSING & PRECISION
# ═══════════════════════════════════════════════════════════════════

def _parse_decimal(val: Any) -> Optional[Decimal]:
    """Herhangi bir değeri güvenli bir şekilde Decimal'e çevirir."""
    if val is None: return None
    try:
        # Eğer string ise temizle (virgül, para birimi vb.)
        if isinstance(val, str):
            clean_val = re.sub(r'[^\d.]', '', val.replace(',', ''))
            return Decimal(clean_val) if clean_val else None
        return Decimal(str(val))
    except Exception as e:
        log.debug(f"Decimal parse hatası ('{val}'): {e}")
        return None

async def _async_call(fn, *args, **kwargs) -> Any:
    """Sync fonksiyonu async-safe şekilde çalıştırır."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

# ═══════════════════════════════════════════════════════════════════
# UYARI KONTROL DÖNGÜSÜ — ✅ ROBUST & HIERARCHICAL
# ═══════════════════════════════════════════════════════════════════

async def uyari_kontrol_dongusu(bot):
    """
    Arka planda fiyat ve RSI uyarılarını kontrol eder.
    ✅ MİMARİ İYİLEŞTİRME:
    - Hiyerarşik veri çekme (SEC -> FMP -> yFinance) entegre edildi.
    - Decimal ile finansal hassasiyet sağlandı.
    - Kademeli kontrol için altyapı hazırlandı.
    """
    log.info("🔔 Uyarı kontrol döngüsü başlatıldı.")
    
    while True:
        try:
            # Tüm aktif uyarıları çek
            uyarilar = await uyarilari_getir()
            if not uyarilar:
                await asyncio.sleep(60)
                continue

            log.debug(f"Kontrol edilecek uyarı sayısı: {len(uyarilar)}")
            
            for uyari in uyarilar:
                try:
                    await _uyari_islem_yap(bot, uyari)
                    # API limitlerini korumak için her uyarı arası kısa bekleme
                    await asyncio.sleep(2)
                except Exception as e:
                    log.error(f"Tekil uyarı işleme hatası: {e}")

            # Döngü arası bekleme (Dinamikleştirilebilir)
            await asyncio.sleep(300) # 5 dakika
            
        except asyncio.CancelledError:
            log.info("🛑 Uyarı kontrol döngüsü iptal edildi.")
            break
        except Exception as e:
            log.exception(f"💥 Uyarı döngüsünde beklenmedik hata: {e}")
            await asyncio.sleep(60)

async def _uyari_islem_yap(bot, uyari: Dict[str, Any]):
    sembol = uyari['sembol']
    user_id = uyari['user_id']
    tip = uyari['tip']
    hedef = _parse_decimal(uyari['hedef_deger'])
    uyari_id = uyari['id']

    if hedef is None:
        log.warning(f"Hedef değer geçersiz: {uyari['hedef_deger']} (ID: {uyari_id})")
        return

    tetiklendi = False
    mesaj = ""
    mevcut_deger = None

    # 1. Fiyat Uyarıları (Hiyerarşik Veri Çekme)
    if tip.startswith('fiyat'):
        fiyat_verisi = await get_fiyat_hiyerarsik(sembol)
        mevcut_deger = _parse_decimal(fiyat_verisi.get("fiyat"))
        
        if mevcut_deger is not None:
            if tip == 'fiyat_ust' and mevcut_deger >= hedef:
                tetiklendi = True
                mesaj = f"🚀 <b>Fiyat Uyarısı!</b>\n{sembol} fiyatı {hedef} üzerine çıktı.\nGüncel: {mevcut_deger:.2f}"
            elif tip == 'fiyat_alt' and mevcut_deger <= hedef:
                tetiklendi = True
                mesaj = f"⚠️ <b>Fiyat Uyarısı!</b>\n{sembol} fiyatı {hedef} altına düştü.\nGüncel: {mevcut_deger:.2f}"

    # 2. Teknik Uyarılar (RSI vb.)
    elif tip.startswith('rsi'):
        teknik = await _async_call(teknik_analiz_yap, sembol)
        mevcut_deger = _parse_decimal(teknik.get('RSI (14)'))
        
        if mevcut_deger is not None:
            if tip == 'rsi_ust' and mevcut_deger >= hedef:
                tetiklendi = True
                mesaj = f"📈 <b>RSI Uyarısı!</b>\n{sembol} RSI değeri {hedef} üzerine çıktı.\nGüncel RSI: {mevcut_deger:.2f}"
            elif tip == 'rsi_alt' and mevcut_deger <= hedef:
                tetiklendi = True
                mesaj = f"📉 <b>RSI Uyarısı!</b>\n{sembol} RSI değeri {hedef} altına düştü.\nGüncel RSI: {mevcut_deger:.2f}"

    # 3. Tetiklenme Durumu
    if tetiklendi and mesaj:
        try:
            await bot.send_message(user_id, mesaj, parse_mode="HTML")
            await uyari_sil(uyari_id)
            log.info(f"✅ Uyarı tetiklendi: {sembol} (ID: {uyari_id})")
        except Exception as e:
            log.error(f"Mesaj gönderilemedi (User: {user_id}): {e}")
