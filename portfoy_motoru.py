
import logging
from db import portfoy_getir
from veri_motoru import alphavantage_fiyat

log = logging.getLogger("portfoy_motoru")

async def portfoy_ozeti_hazirla(user_id: int) -> str:
    """Kullanıcının portföy özetini hazırlar."""
    portfoy = await portfoy_getir(user_id)
    if not portfoy:
        return "📭 Portföyünüz henüz boş. /portfoy_ekle komutu ile varlık ekleyebilirsiniz."

    toplam_maliyet = 0
    toplam_deger = 0
    mesaj = "📊 <b>Portföy Özetiniz</b>\n"
    mesaj += "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"

    for varlik in portfoy:
        sembol = varlik['sembol']
        miktar = varlik['miktar']
        maliyet = varlik['maliyet']
        
        fiyat_verisi = alphavantage_fiyat(sembol)
        if fiyat_verisi and 'Fiyat' in fiyat_verisi:
            guncel_fiyat = float(fiyat_verisi['Fiyat'].split()[0].replace(',', ''))
            guncel_deger = miktar * guncel_fiyat
            maliyet_toplam = miktar * maliyet
            kar_zarar = guncel_deger - maliyet_toplam
            kar_zarar_yuzde = (kar_zarar / maliyet_toplam) * 100 if maliyet_toplam > 0 else 0
            
            emoji = "🟢" if kar_zarar >= 0 else "🔴"
            mesaj += f"{emoji} <b>{sembol}</b>: {miktar} adet\n"
            mesaj += f"   Maliyet: {maliyet:,.2f} | Güncel: {guncel_fiyat:,.2f}\n"
            mesaj += f"   K/Z: {kar_zarar:,.2f} (%{kar_zarar_yuzde:+.2f})\n\n"
            
            toplam_maliyet += maliyet_toplam
            toplam_deger += guncel_deger
        else:
            mesaj += f"⚠️ <b>{sembol}</b>: Fiyat verisi alınamadı.\n\n"

    toplam_kar_zarar = toplam_deger - toplam_maliyet
    toplam_kar_zarar_yuzde = (toplam_kar_zarar / toplam_maliyet) * 100 if toplam_maliyet > 0 else 0
    
    mesaj += "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
    mesaj += f"💰 <b>Toplam Değer:</b> {toplam_deger:,.2f}\n"
    mesaj += f"📈 <b>Toplam K/Z:</b> {toplam_kar_zarar:,.2f} (%{toplam_kar_zarar_yuzde:+.2f})"
    
    return mesaj
