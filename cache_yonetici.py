"""
cache_yonetici.py — yFinance bayat veri sorunlarına karşı merkezi önlem modülü.

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
import yfinance as yf

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
#  UYGULAMA SEVİYESİ CACHE
# ─────────────────────────────────────────────

_kilit   = threading.Lock()
_cache: dict[str, float] = {}   # sembol → son_cekilis_timestamp


def _ttl_gecti_mi(sembol: str) -> bool:
    """True ise TTL dolmuş, veri yenilenmeli."""
    son = _cache.get(sembol.upper(), 0)
    return (time.time() - son) > TTL_SANIYE


def _cache_guncelle(sembol: str):
    with _kilit:
        _cache[sembol.upper()] = time.time()


# ─────────────────────────────────────────────
#  DİSK CACHE TEMİZLEME
# ─────────────────────────────────────────────

def cache_temizle(sadece_sembol: str | None = None):
    """
    yFinance disk cache'ini temizler.
    sadece_sembol=None → tüm cache silinir (bot başlangıcında).
    sadece_sembol="ASELS.IS" → sadece o sembolle ilgili dosyalar silinir.
    """
    try:
        if not os.path.exists(_YFINANCE_CACHE_KLASORU):
            return

        if sadece_sembol is None:
            # Tüm cache klasörünü sil ve yeniden oluştur
            shutil.rmtree(_YFINANCE_CACHE_KLASORU, ignore_errors=True)
            os.makedirs(_YFINANCE_CACHE_KLASORU, exist_ok=True)
        else:
            # Sembol adı geçen dosyaları/kayıtları temizle
            temiz = sadece_sembol.upper().replace(".IS", "")
            for dosya in os.listdir(_YFINANCE_CACHE_KLASORU):
                if temiz in dosya.upper():
                    tam_yol = os.path.join(_YFINANCE_CACHE_KLASORU, dosya)
                    try:
                        if os.path.isfile(tam_yol):
                            os.remove(tam_yol)
                        elif os.path.isdir(tam_yol):
                            shutil.rmtree(tam_yol, ignore_errors=True)
                    except Exception:
                        pass

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
                                cur.execute(
                                    f"DELETE FROM \"{tablo}\" WHERE "
                                    f"UPPER(symbol) LIKE ?",
                                    (f"%{temiz}%",)
                                )
                            except Exception:
                                pass
                        con.commit()
            except Exception:
                pass

    except Exception:
        pass   # Cache temizleme hiçbir zaman ana akışı durdurmasın


# ─────────────────────────────────────────────
#  TAZE TICKER OLUŞTURMA
# ─────────────────────────────────────────────

def taze_ticker(sembol: str) -> yf.Ticker:
    """
    Her zaman taze veri döndüren Ticker fabrika fonksiyonu.

    - TTL dolmuşsa önce disk cache temizler, sonra yeni Ticker döner.
    - TTL dolmamışsa disk cache temizlemeden yeni Ticker döner
      (session cache sıfırlansın diye yine de yeni obje oluşturur).
    - Tüm Ticker() çağrıları bu fonksiyon üzerinden yapılmalı.
    """
    sembol_upper = sembol.upper()

    if _ttl_gecti_mi(sembol_upper):
        # TTL doldu → disk cache'i de temizle
        cache_temizle(sadece_sembol=sembol_upper)
        _cache_guncelle(sembol_upper)

    # Her seferinde yeni Ticker objesi — session-level cache'i atlatır
    return yf.Ticker(sembol_upper)


# ─────────────────────────────────────────────
#  BOT BAŞLANGIÇ TEMİZLİĞİ
# ─────────────────────────────────────────────

def baslangic_temizligi():
    """
    main.py'de bot başlarken bir kez çağrılır.
    Bir önceki çalışmadan kalan tüm disk cache'i siler.
    """
    cache_temizle(sadece_sembol=None)
    with _kilit:
        _cache.clear()


# ─────────────────────────────────────────────
#  TTL SORGULAMA (opsiyonel bilgi amaçlı)
# ─────────────────────────────────────────────

def cache_durumu(sembol: str) -> dict:
    """Debug için: sembolün cache durumunu döner."""
    son = _cache.get(sembol.upper(), 0)
    gecen = time.time() - son if son else None
    return {
        "sembol":        sembol.upper(),
        "son_cekilis":   time.strftime("%H:%M:%S", time.localtime(son)) if son else "hiç",
        "gecen_saniye":  round(gecen, 1) if gecen else None,
        "ttl_doldu_mu":  _ttl_gecti_mi(sembol.upper()),
        "ttl_ayar":      TTL_SANIYE,
    }
