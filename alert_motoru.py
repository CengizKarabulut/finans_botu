
import asyncio
import logging
from db import uyarilari_getir, uyari_sil
from veri_motoru import alphavantage_fiyat
from teknik_analiz import teknik_analiz_yap

log = logging.getLogger("alert_motoru")

async def uyari_kontrol_dongusu(bot):
    """Arka planda fiyat ve RSI uyarılarını kontrol eder."""
    log.info("Uyarı kontrol döngüsü başlatıldı.")
    while True:
        try:
            uyarilar = await uyarilari_getir()
            for uyari in uyarilar:
                sembol = uyari['sembol']
                user_id = uyari['user_id']
                tip = uyari['tip']
                hedef = uyari['hedef_deger']
                uyari_id = uyari['id']

                tetiklendi = False
                mesaj = ""

                if tip.startswith('fiyat'):
                    # Fiyat kontrolü
                    fiyat_verisi = alphavantage_fiyat(sembol)
                    if fiyat_verisi and 'Fiyat' in fiyat_verisi:
                        # Fiyat string formatında gelebilir (örn: "150.00 USD")
                        mevcut_fiyat = float(fiyat_verisi['Fiyat'].split()[0].replace(',', ''))
                        
                        if tip == 'fiyat_ust' and mevcut_fiyat >= hedef:
                            tetiklendi = True
                            mesaj = f"🚀 <b>Fiyat Uyarısı!</b>\n{sembol} fiyatı {hedef} üzerine çıktı.\nGüncel: {mevcut_fiyat}"
                        elif tip == 'fiyat_alt' and mevcut_fiyat <= hedef:
                            tetiklendi = True
                            mesaj = f"⚠️ <b>Fiyat Uyarısı!</b>\n{sembol} fiyatı {hedef} altına düştü.\nGüncel: {mevcut_fiyat}"
                
                elif tip.startswith('rsi'):
                    # RSI kontrolü
                    teknik = teknik_analiz_yap(sembol)
                    if teknik and 'RSI (14)' in teknik:
                        # RSI formatı: "45.23 (Hareketli Ort: 42.10)"
                        mevcut_rsi = float(teknik['RSI (14)'].split()[0])
                        
                        if tip == 'rsi_ust' and mevcut_rsi >= hedef:
                            tetiklendi = True
                            mesaj = f"📈 <b>RSI Uyarısı!</b>\n{sembol} RSI değeri {hedef} üzerine çıktı.\nGüncel RSI: {mevcut_rsi}"
                        elif tip == 'rsi_alt' and mevcut_rsi <= hedef:
                            tetiklendi = True
                            mesaj = f"📉 <b>RSI Uyarısı!</b>\n{sembol} RSI değeri {hedef} altına düştü.\nGüncel RSI: {mevcut_rsi}"

                if tetiklendi:
                    try:
                        await bot.send_message(user_id, mesaj, parse_mode="HTML")
                        await uyari_sil(uyari_id) # Tek seferlik uyarı
                        log.info(f"Uyarı tetiklendi ve silindi: {uyari_id} for user {user_id}")
                    except Exception as e:
                        log.error(f"Mesaj gönderilemedi (User: {user_id}): {e}")

            # API limitlerini zorlamamak için bekleme (örn: 5 dakika)
            await asyncio.sleep(300) 
        except Exception as e:
            log.error(f"Uyarı döngüsünde hata: {e}")
            await asyncio.sleep(60)
