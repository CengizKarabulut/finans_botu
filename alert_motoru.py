"""
alert_motoru.py — Fiyat ve RSI uyarılarını arka planda kontrol eder.
✅ DÜZELTİLMİŞ VERSİYON - Async safety, error handling ve robust parsing eklendi
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any
from db import uyarilari_getir, uyari_sil
from veri_motoru import alphavantage_fiyat
from teknik_analiz import teknik_analiz_yap

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR — ✅ ROBUST PARSING
# ═══════════════════════════════════════════════════════════════════

def _parse_fiyat(fiyat_str: str) -> Optional[float]:
    """
    Fiyat string'ini float'a çevirir.
    Örnek: "150.00 USD" → 150.0, "1,234.56 TL" → 1234.56
    ✅ DÜZELTİLDİ: Regex ile daha robust parsing
    """
    if not fiyat_str or not isinstance(fiyat_str, str):
        return None
    try:
        # Sadece sayısal kısmı ve ondalık ayracı al
        match = re.search(r'[\d,]+\.?\d*', fiyat_str.replace(',', ''))
        if match:
            return float(match.group())
    except (ValueError, AttributeError) as e:
        log.debug(f"Fiyat parse hatası ('{fiyat_str}'): {e}")
    return None


def _parse_rsi(rsi_str: str) -> Optional[float]:
    """
    RSI string'ini float'a çevirir.
    Örnek: "45.23 (Hareketli Ort: 42.10)" → 45.23
    ✅ DÜZELTİLDİ: Hata handling eklendi
    """
    if not rsi_str or not isinstance(rsi_str, str):
        return None
    try:
        # İlk sayısal değeri al
        match = re.search(r'[\d.]+', rsi_str)
        if match:
            return float(match.group())
    except (ValueError, AttributeError) as e:
        log.debug(f"RSI parse hatası ('{rsi_str}'): {e}")
    return None


async def _async_call(fn, *args, **kwargs) -> Any:
    """
    Sync fonksiyonu async-safe şekilde çalıştırır.
    ✅ YENİ: Blocking call'leri event loop'u bloklamadan çalıştırır
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ═══════════════════════════════════════════════════════════════════
# UYARI KONTROL DÖNGÜSÜ — ✅ ASYNC-SAFE + ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════

async def uyari_kontrol_dongusu(bot):
    """
    Arka planda fiyat ve RSI uyarılarını kontrol eder.
    ✅ DÜZELTİLDİ: 
    - Sync fonksiyonlar run_in_executor ile async-safe hale getirildi
    - Robust parsing eklendi
    - Error handling ve logging iyileştirildi
    - API rate limiting için küçük delay'ler eklendi
    """
    log.info("🔔 Uyarı kontrol döngüsü başlatıldı.")
    
    while True:
        try:
            # Uyarıları veritabanından çek
            uyarilar = await uyarilari_getir()
            log.debug(f"Kontrol edilecek uyarı sayısı: {len(uyarilar)}")
            
            for i, uyari in enumerate(uyarilar):
                try:
                    sembol = uyari['sembol']
                    user_id = uyari['user_id']
                    tip = uyari['tip']
                    hedef = float(uyari['hedef_deger'])  # Hedef zaten numeric olmalı
                    uyari_id = uyari['id']

                    tetiklendi = False
                    mesaj = ""
                    mevcut_deger = None

                    # ────────────────────────────────────────────────
                    # FİYAT KONTROLÜ
                    # ────────────────────────────────────────────────
                    if tip.startswith('fiyat'):
                        # ✅ DÜZELTİLDİ: Sync fonksiyon async-safe çağrıldı
                        fiyat_verisi = await _async_call(alphavantage_fiyat, sembol)
                        
                        if fiyat_verisi and 'Fiyat' in fiyat_verisi:
                            mevcut_deger = _parse_fiyat(fiyat_verisi['Fiyat'])
                            
                            if mevcut_deger is not None:
                                if tip == 'fiyat_ust' and mevcut_deger >= hedef:
                                    tetiklendi = True
                                    mesaj = (
                                        f"🚀 <b>Fiyat Uyarısı!</b>\n"
                                        f"{sembol} fiyatı {hedef} üzerine çıktı.\n"
                                        f"Güncel: {mevcut_deger:.2f}"
                                    )
                                elif tip == 'fiyat_alt' and mevcut_deger <= hedef:
                                    tetiklendi = True
                                    mesaj = (
                                        f"⚠️ <b>Fiyat Uyarısı!</b>\n"
                                        f"{sembol} fiyatı {hedef} altına düştü.\n"
                                        f"Güncel: {mevcut_deger:.2f}"
                                    )
                    
                    # ────────────────────────────────────────────────
                    # RSI KONTROLÜ
                    # ────────────────────────────────────────────────
                    elif tip.startswith('rsi'):
                        # ✅ DÜZELTİLDİ: Sync fonksiyon async-safe çağrıldı
                        teknik = await _async_call(teknik_analiz_yap, sembol)
                        
                        if teknik and 'RSI (14)' in teknik:
                            mevcut_deger = _parse_rsi(teknik['RSI (14)'])
                            
                            if mevcut_deger is not None:
                                if tip == 'rsi_ust' and mevcut_deger >= hedef:
                                    tetiklendi = True
                                    mesaj = (
                                        f"📈 <b>RSI Uyarısı!</b>\n"
                                        f"{sembol} RSI değeri {hedef} üzerine çıktı.\n"
                                        f"Güncel RSI: {mevcut_deger:.2f}"
                                    )
                                elif tip == 'rsi_alt' and mevcut_deger <= hedef:
                                    tetiklendi = True
                                    mesaj = (
                                        f"📉 <b>RSI Uyarısı!</b>\n"
                                        f"{sembol} RSI değeri {hedef} altına düştü.\n"
                                        f"Güncel RSI: {mevcut_deger:.2f}"
                                    )

                    # ────────────────────────────────────────────────
                    # UYARI TETİKLENDİ İSE MESAJ GÖNDER
                    # ────────────────────────────────────────────────
                    if tetiklendi and mesaj:
                        try:
                            await bot.send_message(user_id, mesaj, parse_mode="HTML")
                            await uyari_sil(uyari_id)  # Tek seferlik uyarı
                            log.info(f"✅ Uyarı tetiklendi ve silindi: ID={uyari_id}, User={user_id}, Sembol={sembol}, Değer={mevcut_deger}")
                        except Exception as e:
                            log.exception(f"❌ Mesaj gönderilemedi (User: {user_id}, Uyarı: {uyari_id}): {e}")
                            # Mesaj gönderilemezse uyarıyı silme, tekrar denensin
                    
                    # API rate limiting: Her uyarı arasında küçük delay
                    await asyncio.sleep(1)
                    
                except KeyError as e:
                    log.warning(f"⚠️ Uyarı veri yapısı eksik: {e} — Uyari: {uyari}")
                    continue
                except Exception as e:
                    log.exception(f"❌ Uyarı işleme hatası (Sembol: {sembol}, Tip: {tip}): {e}")
                    continue

            # ────────────────────────────────────────────────
            # DÖNGÜ ARASI BEKLEME (API limitlerini korumak için)
            # ────────────────────────────────────────────────
            log.debug("🔁 Uyarı döngüsü tamamlandı, 5 dakika bekleniyor...")
            await asyncio.sleep(300)  # 5 dakika
            
        except asyncio.CancelledError:
            log.info("🛑 Uyarı kontrol döngüsü iptal edildi.")
            break
        except Exception as e:
            log.exception(f"💥 Uyarı döngüsünde beklenmedik hata: {e}")
            # Kritik hata durumunda kısa bekleme ile retry
            await asyncio.sleep(60)
