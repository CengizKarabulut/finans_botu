"""
portfoy_motoru.py — Kullanıcı portföy takibi ve kar/zarar hesaplama.
✅ MİMARİ GÜNCELLEME - Decimal hassasiyeti, get_fiyat_hiyerarsik entegrasyonu.
"""
import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any, List

from db import portfoy_getir, portfoy_ekle, portfoy_sil
from veri_motoru import get_fiyat_hiyerarsik

log = logging.getLogger("finans_botu")


def _parse_decimal(val: Any) -> Optional[Decimal]:
    """Değeri güvenle Decimal'e çevirir."""
    if val is None:
        return None
    try:
        if isinstance(val, str):
            temiz = val.strip().replace(',', '.')
            return Decimal(temiz) if temiz else None
        return Decimal(str(val))
    except (InvalidOperation, ValueError) as e:
        log.debug(f"Decimal parse hatası ('{val}'): {e}")
        return None


async def portfoy_ozeti_hazirla(user_id: int) -> str:
    """
    Kullanıcının portföy özetini hazırlar.
    ✅ Decimal hassasiyeti, asenkron fiyat çekimi.
    """
    portfoy = await portfoy_getir(user_id)
    if not portfoy:
        return (
            "📭 <b>Portföyünüz henüz boş.</b>\n\n"
            "Varlık eklemek için:\n"
            "<code>/portfoy_ekle THYAO 100 45.50</code>\n"
            "(Sembol, Miktar, Alış Maliyeti)"
        )

    toplam_maliyet = Decimal("0")
    toplam_deger = Decimal("0")
    mesaj = "📊 <b>Portföy Özetiniz</b>\n"
    mesaj += "┄" * 22 + "\n"

    # Tüm sembollerin fiyatlarını paralel çek
    semboller = list({v['sembol'] for v in portfoy})
    fiyat_gorevleri = {s: get_fiyat_hiyerarsik(s) for s in semboller}
    fiyat_sonuclari: Dict[str, Dict[str, Any]] = {}
    for sembol, gorev in fiyat_gorevleri.items():
        try:
            fiyat_sonuclari[sembol] = await gorev
        except Exception as e:
            log.error(f"Portföy fiyat çekme hatası ({sembol}): {e}")
            fiyat_sonuclari[sembol] = {}

    for varlik in portfoy:
        sembol = varlik['sembol']
        miktar = _parse_decimal(varlik['miktar'])
        maliyet = _parse_decimal(varlik['maliyet'])

        if miktar is None or maliyet is None:
            mesaj += f"⚠️ <b>{sembol}</b>: Geçersiz veri.\n\n"
            continue

        fiyat_verisi = fiyat_sonuclari.get(sembol, {})
        guncel_fiyat_raw = fiyat_verisi.get("fiyat")
        guncel_fiyat = _parse_decimal(guncel_fiyat_raw)

        if guncel_fiyat is not None:
            guncel_deger = miktar * guncel_fiyat
            maliyet_toplam = miktar * maliyet
            kar_zarar = guncel_deger - maliyet_toplam
            kar_zarar_yuzde = (kar_zarar / maliyet_toplam * 100) if maliyet_toplam > 0 else Decimal("0")

            emoji = "🟢" if kar_zarar >= 0 else "🔴"
            mesaj += f"{emoji} <b>{sembol}</b>: {miktar:f} adet\n"
            mesaj += f"   Maliyet: {maliyet:.2f} | Güncel: {guncel_fiyat:.2f}\n"
            mesaj += f"   K/Z: {kar_zarar:+.2f} (%{kar_zarar_yuzde:+.2f})\n\n"

            toplam_maliyet += maliyet_toplam
            toplam_deger += guncel_deger
        else:
            mesaj += f"⚠️ <b>{sembol}</b>: Fiyat verisi alınamadı.\n\n"

    toplam_kar_zarar = toplam_deger - toplam_maliyet
    toplam_kar_zarar_yuzde = (
        (toplam_kar_zarar / toplam_maliyet * 100) if toplam_maliyet > 0 else Decimal("0")
    )

    mesaj += "┄" * 22 + "\n"
    mesaj += f"💰 <b>Toplam Değer:</b> {toplam_deger:.2f}\n"
    mesaj += f"📈 <b>Toplam K/Z:</b> {toplam_kar_zarar:+.2f} (%{toplam_kar_zarar_yuzde:+.2f})"

    return mesaj


async def portfoy_varlik_ekle(user_id: int, sembol: str, miktar: str, maliyet: str) -> str:
    """
    Portföye yeni varlık ekler veya mevcut kaydı günceller.
    Döndürür: Kullanıcıya gösterilecek mesaj.
    """
    # Değerleri doğrula
    miktar_d = _parse_decimal(miktar)
    maliyet_d = _parse_decimal(maliyet)

    if miktar_d is None or miktar_d <= 0:
        return "❌ Geçersiz miktar. Örnek: <code>/portfoy_ekle THYAO 100 45.50</code>"
    if maliyet_d is None or maliyet_d <= 0:
        return "❌ Geçersiz maliyet. Örnek: <code>/portfoy_ekle THYAO 100 45.50</code>"

    try:
        await portfoy_ekle(user_id, sembol, str(miktar_d), str(maliyet_d))
        return (
            f"✅ <b>{sembol.upper()}</b> portföye eklendi.\n"
            f"Miktar: {miktar_d:f} | Maliyet: {maliyet_d:.2f}"
        )
    except Exception as e:
        log.error(f"Portföy ekleme hatası ({sembol}): {e}")
        return f"❌ Portföy güncellenemedi: {str(e)}"


async def portfoy_varlik_sil(user_id: int, sembol: str) -> str:
    """Portföyden varlık siler."""
    try:
        await portfoy_sil(user_id, sembol)
        return f"✅ <b>{sembol.upper()}</b> portföyden silindi."
    except Exception as e:
        log.error(f"Portföy silme hatası ({sembol}): {e}")
        return f"❌ Portföy güncellenemedi: {str(e)}"
