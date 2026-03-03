"""
cache_yonetici.py — yFinance bayat veri sorunlarına karşı merkezi önlem modülü.
✅ DÜZELTİLMİŞ VERSİYON - Thread-safety, logging ve error handling eklendi

Sorunlar ve çözümleri:
  1. yFinance disk cache (~/.cache/py-yfinance/ SQLite)
       → Bot başlarken ve isteğe bağlı olarak temizlenir.
  2. yFinance HTTP session cache (aynı process içinde tekrar sorgularda)
       → Her Ticker() çağrısı için yeni session oluşturulur.
  3. Uygulama seviyesi tekrar sorgu koruması
       → Aynı sembol TTL_SANIYE içinde tekrar çekilirse önbellekten döner,
          TTL geçince zorla yeni Ticker() + disk cache temizleme yapılır.

Kullanım (teknik_analiz.py ve temel_analiz.py başında):
    from cache_yonetici import taze_ticker, cache_temizle
    hisse = taze_ticker("ASELS.IS")   # yeni, temiz Ticker objesi
"""

import os
import time
import shutil
import threading
import logging
import yfinance as yf
from typing import Optional

# ═══════════════════════════════════════════════════════════════════
# LOGGING SETUP — ✅ EKLENDİ
# ═══════════════════════════════════════════════════════════════════
log = logging.getLogger("finans_botu")

# ─────────────────────────────────────────────
#  AYARLAR
# ─────────────────────────────────────────────

# Aynı sembol kaç saniye sonra yeniden çekilsin (300 = 5 dakika)
TTL_SANIYE = 300

# yFinance disk cache klasörü (tüm platformlarda çalışır)
_YFINANCE_CACHE_KLASORU = os.path.join(
    os.path.expanduser("~"), ".cache", "py-yfinance"
)

# ─────────────────────────────────────────────
#  UYGULAMA SEVİYESİ CACHE — ✅ THREAD-SAFE
# ─────────────────────────────────────────────

_kilit   = threading.Lock()
_cache: dict[str, float] = {}   # sembol → son_cekilis_timestamp


def _ttl_gecti_mi(sembol: str) -> bool:
    """
    True ise TTL dolmuş, veri yenilenmeli.
    ✅ DÜZELTİLDİ: Lock ile thread-safe okuma
    """
    with _kilit:  # ✅ Thread-safe okuma
        son = _cache.get(sembol.upper(), 0)
    return (time.time() - son) > TTL_SANIYE


def _cache_guncelle(sembol: str):
    """Cache timestamp'ini güncelle — thread-safe."""
    with _kilit:
        _cache[sembol.upper()] = time.time()
        log.debug(f"Cache güncellendi: {sembol.upper()}")


# ─────────────────────────────────────────────
#  DİSK CACHE TEMİZLEME — ✅ LOGGING + ERROR HANDLING
# ─────────────────────────────────────────────

def cache_temizle(sadece_sembol: Optional[str] = None):
    """
    yFinance disk cache'ini temizler.
    sadece_sembol=None → tüm cache silinir (bot başlangıcında).
    sadece_sembol="ASELS.IS" → sadece o sembolle ilgili dosyalar silinir.
    ✅ DÜZELTİLDİ: Logging eklendi, silent pass kaldırıldı
    """
    try:
        if not os.path.exists(_YFINANCE_CACHE_KLASORU):
            log.debug(f"Cache klasörü yok: {_YFINANCE_CACHE_KLASORU}")
            return

        if sadece_sembol is None:
            # Tüm cache klasörünü sil ve yeniden oluştur
            log.info("Tüm yFinance cache temizleniyor...")
            shutil.rmtree(_YFINANCE_CACHE_KLASORU, ignore_errors=True)
            os.makedirs(_YFINANCE_CACHE_KLASORU, exist_ok=True)
            log.info("Cache klasörü yeniden oluşturuldu")
        else:
            # Sembol adı geçen dosyaları/kayıtları temizle
            temiz = sadece_sembol.upper().replace(".IS", "")
            log.debug(f"Cache temizleme: {temiz}")
            
            silinen = 0
            for dosya in os.listdir(_YFINANCE_CACHE_KLASORU):
                if temiz in dosya.upper():
                    tam_yol = os.path.join(_YFINANCE_CACHE_KLASORU, dosya)
                    try:
                        if os.path.isfile(tam_yol):
                            os.remove(tam_yol)
                            silinen += 1
                            log.debug(f"Silindi: {dosya}")
                        elif os.path.isdir(tam_yol):
                            shutil.rmtree(tam_yol, ignore_errors=True)
                            silinen += 1
                            log.debug(f"Klasör silindi: {dosya}")
                    except Exception as e:
                        log.warning(f"Cache dosya silme hatası ({dosya}): {e}")

            log.debug(f"Cache temizleme tamamlandı: {silinen} öğe silindi")

            # SQLite DB içindeki kayıtları da temizle (yfinance >= 0.2.x)
            try:
                import sqlite3
                db_yolu = os.path.join(_YFINANCE_CACHE_KLASORU, "py-yfinance.db")
                if os.path.exists(db_yolu):
                    with sqlite3.connect(db_yolu) as con:
                        cur = con.cursor()
                        cur.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                        tablolar = [r[0] for r in cur.fetchall()]
                        for tablo in tablolar:
                            try:
                                # ✅ FIX: Table name validation + parameterized query
                                if not tablo.isidentifier():
                                    continue
                                cur.execute(
                                    f'DELETE FROM "{tablo}" WHERE UPPER(symbol) LIKE ?',
                                    (f"%{temiz}%",)
                                )
                            except Exception as e:
                                log.debug(f"SQLite DELETE hatası ({tablo}): {e}")
                        con.commit()
                    log.debug(f"SQLite cache temizlendi: {db_yolu}")
            except ImportError:
                log.debug("sqlite3 bulunamadı, DB temizleme atlandı")
            except Exception as e:
                log.warning(f"SQLite cache temizleme hatası: {e}")

    except Exception as e:
        log.exception(f"cache_temizle genel hata: {e}")
        # ✅ Cache temizleme hiçbir zaman ana akışı durdurmasın


# ─────────────────────────────────────────────
#  TAZE TICKER OLUŞTURMA — ✅ LOGGING
# ─────────────────────────────────────────────

def taze_ticker(sembol: str) -> yf.Ticker:
    """
    Her zaman taze veri döndüren Ticker fabrika fonksiyonu.

    - TTL dolmuşsa önce disk cache temizler, sonra yeni Ticker döner.
    - TTL dolmamışsa disk cache temizlemeden yeni Ticker döner
      (session cache sıfırlansın diye yine de yeni obje oluşturur).
    - Tüm Ticker() çağrıları bu fonksiyon üzerinden yapılmalı.
    ✅ DÜZELTİLDİ: Logging eklendi
    """
    sembol_upper = sembol.upper()

    if _ttl_gecti_mi(sembol_upper):
        # TTL doldu → disk cache'i de temizle
        log.debug(f"TTL doldu, cache temizleniyor: {sembol_upper}")
        cache_temizle(sadece_sembol=sembol_upper)
        _cache_guncelle(sembol_upper)
    else:
        log.debug(f"Cache hit (TTL aktif): {sembol_upper}")

    # Her seferinde yeni Ticker objesi — session-level cache'i atlatır
    return yf.Ticker(sembol_upper)


# ─────────────────────────────────────────────
#  BOT BAŞLANGIÇ TEMİZLİĞİ — ✅ LOGGING
# ─────────────────────────────────────────────

def baslangic_temizligi():
    """
    main.py'de bot başlarken bir kez çağrılır.
    Timezone SQLite DB sorununu da çözer (no such table: _tz_kv).
    ✅ DÜZELTİLDİ: Logging eklendi
    """
    log.info("Cache başlangıç temizliği başlıyor...")
    
    # 1. Ana cache klasörünü temizle
    cache_temizle(sadece_sembol=None)

    # 2. yFinance timezone cache DB'sini sıfırla
    try:
        tz_db_yollari = [
            os.path.join(_YFINANCE_CACHE_KLASORU, "tz-cache.db"),
            os.path.join(_YFINANCE_CACHE_KLASORU, "py-yfinance.db"),
        ]
        for tz_db in tz_db_yollari:
            if os.path.exists(tz_db):
                os.remove(tz_db)
                log.debug(f"Timezone cache silindi: {tz_db}")
        os.makedirs(_YFINANCE_CACHE_KLASORU, exist_ok=True)
    except Exception as e:
        log.warning(f"Timezone cache temizleme hatası: {e}")

    # 3. yFinance tz cache konumunu /tmp'ye yönlendir (yazma izni garantili)
    try:
        yf.set_tz_cache_location("/tmp/yf_tz_cache")
        log.debug("yFinance tz cache location ayarlandı: /tmp/yf_tz_cache")
    except Exception as e:
        log.warning(f"yFinance tz cache location ayarlama hatası: {e}")

    with _kilit:
        _cache.clear()
    
    log.info("Cache başlangıç temizliği tamamlandı")


# ─────────────────────────────────────────────
#  TTL SORGULAMA (opsiyonel bilgi amaçlı) — ✅ LOGGING
# ─────────────────────────────────────────────

def cache_durumu(sembol: str) -> dict:
    """
    Debug için: sembolün cache durumunu döner.
    ✅ DÜZELTİLDİ: Thread-safe okuma
    """
    with _kilit:  # ✅ Thread-safe okuma
        son = _cache.get(sembol.upper(), 0)
    
    gecen = time.time() - son if son else None
    return {
        "sembol":        sembol.upper(),
        "son_cekilis":   time.strftime("%H:%M:%S", time.localtime(son)) if son else "hiç",
        "gecen_saniye":  round(gecen, 1) if gecen else None,
        "ttl_doldu_mu":  (time.time() - son) > TTL_SANIYE if son else True,
        "ttl_ayar":      TTL_SANIYE,
    }


# ─────────────────────────────────────────────
#  DEBUG: Tüm cache durumunu listele
# ─────────────────────────────────────────────

def cache_listele() -> list[dict]:
    """
    Debug için: tüm cache entries'lerini listeler.
    ✅ YENİ: Debug fonksiyonu eklendi
    """
    sonuclar = []
    with _kilit:
        for sembol, ts in _cache.items():
            gecen = time.time() - ts
            sonuclar.append({
                "sembol": sembol,
                "timestamp": ts,
                "gecen_saniye": round(gecen, 1),
                "ttl_doldu_mu": gecen > TTL_SANIYE,
            })
    return sorted(sonuclar, key=lambda x: x["gecen_saniye"], reverse=True)
