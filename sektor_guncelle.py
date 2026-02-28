"""
sektor_guncelle.py — Haftalık otomatik sektör listesi güncelleyici.

Ne yapar:
  1. borsapy'den güncel şirket listesini çeker (775+)
  2. sektor_listesi.json'a bakarak YENİ hisseleri (IPO'lar) tespit eder
  3. Sadece yeni hisselerin bilgilerini çeker — mevcut veriye dokunmaz
  4. Güncellenmiş listeyi kaydeder ve özet rapor yazar

Cron job kurulumu (sunucuda bir kez):
  crontab -e

  # Her Pazar gece yarısı çalıştır:
  0 0 * * 0 /usr/bin/python3 /path/to/sektor_guncelle.py >> /path/to/logs/sektor_guncelle.log 2>&1

Veya manuel çalıştırma:
  python3 sektor_guncelle.py
"""

import json
import time
import os
import sys
from datetime import datetime

# ─────────────────────────────────────────────
#  AYARLAR
# ─────────────────────────────────────────────

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
JSON_DOSYA  = os.path.join(SCRIPT_DIR, "sektor_listesi.json")
LOG_DOSYA   = os.path.join(SCRIPT_DIR, "logs", "sektor_guncelle.log")


def log(mesaj: str):
    zaman = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    satir = f"[{zaman}] {mesaj}"
    print(satir, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_DOSYA), exist_ok=True)
        with open(LOG_DOSYA, "a", encoding="utf-8") as f:
            f.write(satir + "\n")
    except Exception:
        pass


# ─────────────────────────────────────────────
#  MEVCUT LİSTEYİ YÜKLEzŸ
# ─────────────────────────────────────────────

def mevcut_listeyi_yukle() -> dict:
    if not os.path.exists(JSON_DOSYA):
        log("⚠️  sektor_listesi.json bulunamadı. Sıfırdan oluşturulacak.")
        return {}
    try:
        with open(JSON_DOSYA, "r", encoding="utf-8") as f:
            veri = json.load(f)
        log(f"✅ Mevcut liste yüklendi: {len(veri)} hisse")
        return veri
    except Exception as e:
        log(f"❌ JSON okuma hatası: {e}")
        return {}


# ─────────────────────────────────────────────
#  borsapy'DEN GÜNCEL LİSTE
# ─────────────────────────────────────────────

def guncel_tickers_cek() -> list:
    try:
        import borsapy as bp
        sirketler = bp.companies()
        tickers = sirketler["ticker"].tolist()
        log(f"📊 borsapy'den {len(tickers)} ticker alındı")
        return tickers
    except Exception as e:
        log(f"❌ borsapy companies() hatası: {e}")
        sys.exit(1)


# ─────────────────────────────────────────────
#  YENİ HİSSELERİ BELİRLE
# ─────────────────────────────────────────────

def yeni_hisseleri_bul(guncel: list, mevcut: dict) -> list:
    mevcut_set = set(mevcut.keys())
    yeni = [t for t in guncel if t not in mevcut_set]
    if yeni:
        log(f"🆕 {len(yeni)} yeni hisse tespit edildi: {yeni}")
    else:
        log("✅ Yeni hisse yok, liste güncel")
    return yeni


# ─────────────────────────────────────────────
#  YENİ HİSSELERİN BİLGİLERİNİ ÇEK
# ─────────────────────────────────────────────

def yeni_hisseleri_cek(yeni_tickers: list) -> dict:
    if not yeni_tickers:
        return {}

    import borsapy as bp

    eklenenler = {}
    hatalar    = []

    for i, ticker in enumerate(yeni_tickers):
        try:
            info = bp.Ticker(ticker).info
            sektor   = (info.get("sector",   "") or "").strip()
            industry = (info.get("industry", "") or "").strip()
            ad       = (info.get("description", "") or "").strip()
            eklenenler[ticker] = {
                "name":     ad,
                "sector":   sektor,
                "industry": industry,
                "eklendi":  datetime.now().strftime("%Y-%m-%d"),
            }
            log(f"  ✅ {ticker}: {sektor or 'sektör bulunamadı'}")
        except Exception as e:
            log(f"  ❌ {ticker}: {e}")
            hatalar.append(ticker)

        # API'yi yormamak için kısa bekleme
        if (i + 1) % 10 == 0:
            time.sleep(0.5)

    if hatalar:
        log(f"⚠️  {len(hatalar)} hissede hata: {hatalar}")

    return eklenenler


# ─────────────────────────────────────────────
#  KAYDET + YEDEK
# ─────────────────────────────────────────────

def kaydet(guncellenmiş: dict):
    # Önce yedek al
    if os.path.exists(JSON_DOSYA):
        yedek = JSON_DOSYA.replace(".json", "_yedek.json")
        try:
            import shutil
            shutil.copy2(JSON_DOSYA, yedek)
            log(f"📁 Yedek alındı: {yedek}")
        except Exception:
            pass

    with open(JSON_DOSYA, "w", encoding="utf-8") as f:
        json.dump(guncellenmiş, f, ensure_ascii=False, indent=2)
    log(f"💾 sektor_listesi.json güncellendi: {len(guncellenmiş)} hisse")


# ─────────────────────────────────────────────
#  ÖZET RAPOR
# ─────────────────────────────────────────────

def ozet_rapor(mevcut: dict, yeni: dict, guncel_tickers: list):
    log("─" * 50)
    log(f"📋 ÖZET RAPOR — {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    log(f"   borsapy toplam hisse : {len(guncel_tickers)}")
    log(f"   önceki kayıtlı       : {len(mevcut)}")
    log(f"   yeni eklenen         : {len(yeni)}")
    log(f"   güncel toplam        : {len(mevcut) + len(yeni)}")

    if yeni:
        log("   Yeni hisseler:")
        for t, v in yeni.items():
            log(f"     {t:12} → {v.get('sector', '-')}")

    # Sektör dağılımı (özet)
    tum = {**mevcut, **yeni}
    sektorler = {}
    for v in tum.values():
        s = v.get("sector") or "Bilinmiyor"
        sektorler[s] = sektorler.get(s, 0) + 1
    log(f"   Sektör sayısı: {len(sektorler)}")
    log("─" * 50)


# ─────────────────────────────────────────────
#  ANA AKIŞ
# ─────────────────────────────────────────────

def main():
    log("=" * 50)
    log("🚀 sektor_guncelle.py başladı")
    log("=" * 50)

    mevcut        = mevcut_listeyi_yukle()
    guncel        = guncel_tickers_cek()
    yeni_tickers  = yeni_hisseleri_bul(guncel, mevcut)
    yeni_veri     = yeni_hisseleri_cek(yeni_tickers)

    if yeni_veri:
        guncellenmiş = {**mevcut, **yeni_veri}
        kaydet(guncellenmiş)
    else:
        log("ℹ️  Değişiklik yok, dosya güncellenmedi")
        guncellenmiş = mevcut

    ozet_rapor(mevcut, yeni_veri, guncel)
    log("✅ Tamamlandı")


if __name__ == "__main__":
    main()
