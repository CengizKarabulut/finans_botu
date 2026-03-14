"""
tradingview_motoru.py — Selenium WebDriver ile TradingView ekran görüntüsü alır.

AKIŞ:
  1. İlk kurulumda: python3 tradingview_motoru.py  veya  python3 main.py --login
     → Görünür Chrome penceresi açılır, kullanıcı elle TradingView'a giriş yapar.
     → Oturum selenium_profile/ dizinine kalıcı olarak kaydedilir.

  2. Normal çalışmada (bot):
     → Headless modda aynı profili kullanır, oturum zaten açık.
     → Sembol gönderilir, grafik yüklenir, screenshot alınır.

✅ Manuel Giriş Desteği: Kullanıcı bir kez giriş yapar, oturum kalıcı olur.
✅ Otomatik Sembol Değiştirme: TradingView search box üzerinden sembol açar.
✅ Temiz Görüntü: UI elemanlarını gizleyerek sadece grafiği yakalar.
✅ async close() — main.py shutdown ile uyumlu.
✅ Session doğrulama — Oturum açık mı kontrolü.
"""
import os
import time
import asyncio
import logging
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import undetected_chromedriver as uc

from config import settings

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════
# AYARLAR
# ═══════════════════════════════════════════════════════════════

# Kalıcı Chrome profil dizini (oturum burada saklanır)
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selenium_profile")

# TradingView kayıtlı layout URL'si (varsa)
# Örn: https://www.tradingview.com/chart/AbCdEfGh/
# Bu URL, kullanıcının kaydedilmiş layout'unu (indikatörleri, template'i) kullanır.
DEFAULT_CHART_URL = "https://www.tradingview.com/chart/"

# Grafik yüklenme bekleme süreleri (saniye)
CHART_LOAD_WAIT = 8       # İlk sayfa yükleme
SYMBOL_CHANGE_WAIT = 8    # Sembol değiştikten sonra grafik yüklenmesi
UI_HIDE_WAIT = 1           # UI gizleme sonrası


# ═══════════════════════════════════════════════════════════════
# SEMBOL FORMATLAMA
# ═══════════════════════════════════════════════════════════════

def _tv_sembol_formatla(sembol: str) -> str:
    """
    Sembolü TradingView arama kutusuna yazılacak formata çevirir.
    
    THYAO.IS  → BIST:THYAO
    BTC-USD   → BTCUSD
    AAPL      → AAPL
    EURUSD=X  → EURUSD
    GC=F      → COMEX:GC1!
    """
    s = sembol.upper().strip()
    
    # BIST hisseleri
    if s.endswith(".IS"):
        return "BIST:" + s.replace(".IS", "")
    
    # Kripto (ayraçlı)
    if "-" in s:
        return s.replace("-", "")
    
    # Forex (yFinance formatı)
    if s.endswith("=X"):
        return s.replace("=X", "")
    
    # Emtia vadeli (yFinance formatı → TradingView)
    _EMTIA_TV_MAP = {
        "GC=F": "COMEX:GC1!",    # Altın
        "SI=F": "COMEX:SI1!",    # Gümüş
        "CL=F": "NYMEX:CL1!",   # Ham petrol
        "BZ=F": "NYMEX:BZ1!",   # Brent
        "NG=F": "NYMEX:NG1!",   # Doğalgaz
        "HG=F": "COMEX:HG1!",   # Bakır
        "PL=F": "NYMEX:PL1!",   # Platin
        "ES=F": "CME_MINI:ES1!", # S&P 500 Futures
        "NQ=F": "CME_MINI:NQ1!", # Nasdaq Futures
        "ZC=F": "CBOT:ZC1!",    # Mısır
        "ZW=F": "CBOT:ZW1!",    # Buğday
        "KC=F": "NYMEX:KC1!",   # Kahve
    }
    if s in _EMTIA_TV_MAP:
        return _EMTIA_TV_MAP[s]
    
    # Diğer vadeli işlemler
    if s.endswith("=F"):
        return s.replace("=F", "1!")
    
    return s


# ═══════════════════════════════════════════════════════════════
# TARAYICI YÖNETİMİ (Singleton)
# ═══════════════════════════════════════════════════════════════

class TVBrowser:
    """
    Singleton Chrome WebDriver yöneticisi.
    Aynı profil dizinini kullanarak oturumu korur.
    """
    _driver = None
    _lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    @classmethod
    def _ensure_lock(cls):
        """Lazy lock — event loop başlamadan önce çağrılabilir."""
        if cls._lock is None:
            try:
                cls._lock = asyncio.Lock()
            except RuntimeError:
                pass

    @classmethod
    def get_driver(cls, headless: bool = True):
        """
        Chrome WebDriver döndürür (yoksa oluşturur).
        
        Args:
            headless: True → arka plan (bot modu), False → görünür pencere (login modu)
        """
        if cls._driver is not None:
            # Driver var ama çökmüş olabilir
            try:
                _ = cls._driver.current_url
                return cls._driver
            except Exception:
                log.warning("⚠️ Mevcut WebDriver yanıt vermiyor, yeniden oluşturuluyor...")
                cls._force_quit()

        # Profil dizinini oluştur
        os.makedirs(PROFILE_DIR, exist_ok=True)

        options = uc.ChromeOptions()
        
        if headless:
            options.add_argument("--headless=new")
        
        # Kalıcı profil — oturum burada saklanır
        options.add_argument(f"--user-data-dir={PROFILE_DIR}")
        
        # Stabilite ayarları
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        
        # Bot tespitini engelle
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        try:
            cls._driver = uc.Chrome(options=options, version_main=None)
            # Sayfa yükleme timeout
            cls._driver.set_page_load_timeout(60)
            cls._driver.implicitly_wait(5)
            log.info(f"✅ Selenium WebDriver başlatıldı (headless={headless}).")
            return cls._driver
        except Exception as e:
            log.error(f"❌ WebDriver başlatılamadı: {e}")
            cls._driver = None
            return None

    @classmethod
    def _force_quit(cls):
        """Driver'ı zorla kapat (hata durumlarında)."""
        try:
            if cls._driver:
                cls._driver.quit()
        except Exception:
            pass
        cls._driver = None

    @classmethod
    async def close(cls):
        """Driver'ı asenkron olarak kapat (main.py shutdown ile uyumlu)."""
        if cls._driver:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, cls._driver.quit)
                log.info("🔌 WebDriver kapatıldı.")
            except Exception as e:
                log.warning(f"WebDriver kapatma hatası: {e}")
            finally:
                cls._driver = None


# ═══════════════════════════════════════════════════════════════
# OTURUM KONTROLÜ
# ═══════════════════════════════════════════════════════════════

def _oturum_acik_mi(driver) -> bool:
    """
    TradingView'da oturum açık mı kontrol eder.
    
    Kontrol yöntemleri:
    1. URL'de "signin" geçiyorsa → oturum kapalı
    2. Sayfada kullanıcı menüsü varsa → oturum açık
    """
    try:
        current_url = driver.current_url
        
        # Signin sayfasına yönlendirildiyse
        if "signin" in current_url.lower():
            return False
        
        # Kullanıcı menü butonu var mı?
        selectors = [
            '[data-name="header-user-menu-button"]',
            'button[aria-label="Open user menu"]',
            '.tv-header__user-menu-button',
        ]
        for sel in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    return True
            except Exception:
                continue
        
        # Sayfa kaynağında "Sign in" butonu belirgin mi?
        page_src = driver.page_source[:5000]  # İlk 5KB yeterli
        if 'class="tv-header__link--signin"' in page_src:
            return False
        
        # Grafik sayfasındaysa ve signin yoksa muhtemelen açık
        if "/chart/" in current_url:
            return True
        
        return False
    except Exception as e:
        log.debug(f"Oturum kontrolü hatası: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# GRAFİK ÇEKME (ANA FONKSİYON)
# ═══════════════════════════════════════════════════════════════

async def tv_grafik_cek(sembol: str, output_path: str) -> bool:
    """
    TradingView üzerinden grafik ekran görüntüsü alır.
    
    Args:
        sembol: Hisse/kripto/döviz sembolü (örn: THYAO.IS, BTC-USD, AAPL)
        output_path: Çıktı PNG dosyasının yolu
    
    Returns:
        True: Başarılı, False: Başarısız
    """
    loop = asyncio.get_running_loop()
    
    try:
        # Driver'ı al (headless mod — bot için)
        driver = await loop.run_in_executor(None, lambda: TVBrowser.get_driver(headless=True))
        if not driver:
            log.error("❌ WebDriver oluşturulamadı.")
            return False

        tv_symbol = _tv_sembol_formatla(sembol)
        chart_url = settings.TRADINGVIEW_CHART_URL or DEFAULT_CHART_URL
        
        log.info(f"📊 Grafik açılıyor: {tv_symbol}")

        # Sayfayı aç
        await loop.run_in_executor(None, lambda: driver.get(chart_url))
        await asyncio.sleep(CHART_LOAD_WAIT)

        # Oturum kontrolü
        oturum_ok = await loop.run_in_executor(None, lambda: _oturum_acik_mi(driver))
        if not oturum_ok:
            log.warning(
                "⚠️ TradingView oturumu açık değil!\n"
                "   Çözüm: Sunucuda şu komutu çalıştırın:\n"
                "   python3 tradingview_motoru.py\n"
                "   veya: python3 main.py --login"
            )
            return False

        # Sembol değiştirme
        success = await loop.run_in_executor(
            None, lambda: _sembol_degistir(driver, tv_symbol)
        )
        if not success:
            log.warning(f"⚠️ Sembol değiştirilemedi: {tv_symbol}")
            # Yine de mevcut grafiğin screenshot'ını alalım
        
        await asyncio.sleep(SYMBOL_CHANGE_WAIT)

        # UI elemanlarını gizle (temiz grafik için)
        await loop.run_in_executor(None, lambda: _ui_gizle(driver))
        await asyncio.sleep(UI_HIDE_WAIT)

        # Screenshot al
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        await loop.run_in_executor(None, lambda: driver.save_screenshot(output_path))
        
        log.info(f"✅ Grafik kaydedildi: {output_path}")
        return True

    except Exception as e:
        log.error(f"❌ Grafik çekme hatası ({sembol}): {e}")
        # Driver sorunluysa sıfırla
        TVBrowser._force_quit()
        return False


# ═══════════════════════════════════════════════════════════════
# SEMBOL DEĞİŞTİRME
# ═══════════════════════════════════════════════════════════════

def _sembol_degistir(driver, tv_symbol: str) -> bool:
    """
    TradingView grafik üzerinde sembolü değiştirir.
    
    Yöntem: Klavye kısayolu ile arama kutusunu aç → sembol yaz → Enter
    TradingView'da herhangi bir grafik sayfasında bir tuşa basmak
    otomatik olarak sembol arama kutusunu açar.
    """
    try:
        # Yöntem 1: Doğrudan body'ye sembol yazma (TradingView kısayolu)
        body = driver.find_element(By.TAG_NAME, "body")
        
        # Önce mevcut arama kutusunu temizle (varsa)
        # ESC ile herhangi bir açık dialog'u kapat
        body.send_keys(Keys.ESCAPE)
        time.sleep(0.5)
        
        # Sembolü yaz — TradingView otomatik olarak arama kutusunu açar
        body.send_keys(tv_symbol)
        time.sleep(2)  # Arama sonuçlarının yüklenmesi için
        
        # Enter ile seç
        body.send_keys(Keys.ENTER)
        time.sleep(1)
        
        log.info(f"🔄 Sembol gönderildi: {tv_symbol}")
        return True
        
    except Exception as e:
        log.warning(f"Sembol değiştirme hatası: {e}")
        
        # Yöntem 2: Sembol arama butonuna tıklama
        try:
            search_selectors = [
                '[data-name="symbol-search-btn"]',
                '#header-toolbar-symbol-search',
                'button[aria-label="Symbol Search"]',
                '.tv-header-toolbar__button--search',
            ]
            for sel in search_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, sel)
                    btn.click()
                    time.sleep(1)
                    
                    # Arama input'unu bul ve yaz
                    search_input = driver.find_element(
                        By.CSS_SELECTOR, 
                        'input[data-role="search"], input.search-ZXzPWcCf, input[type="text"]'
                    )
                    search_input.clear()
                    search_input.send_keys(tv_symbol)
                    time.sleep(2)
                    search_input.send_keys(Keys.ENTER)
                    
                    log.info(f"🔄 Sembol arama butonu ile gönderildi: {tv_symbol}")
                    return True
                except Exception:
                    continue
        except Exception as e2:
            log.warning(f"Alternatif sembol değiştirme de başarısız: {e2}")
    
    return False


# ═══════════════════════════════════════════════════════════════
# UI GİZLEME (TEMİZ GRAFİK İÇİN)
# ═══════════════════════════════════════════════════════════════

def _ui_gizle(driver):
    """TradingView UI elemanlarını gizleyerek temiz grafik görüntüsü sağlar."""
    try:
        driver.execute_script("""
            // Gizlenecek UI elemanları
            var selectors = [
                'header',
                '.tv-header',
                '.tv-header--mobile',
                '[data-name="drawing-toolbar"]',
                '.tv-side-toolbar',
                '.layout__area--left',
                '.layout__area--right',
                '.chart-controls-bar',
                '.bottom-widgetbar-content',
                '.tv-feed-widget',
                '.layout__area--bottom',
                // Toolbarlar
                '#header-toolbar-intervals',
                '#drawing-toolbar',
                // Watchlist ve diğer paneller
                '[data-name="right-toolbar"]',
            ];
            
            selectors.forEach(function(s) {
                try {
                    document.querySelectorAll(s).forEach(function(el) {
                        el.style.setProperty('display', 'none', 'important');
                    });
                } catch(e) {}
            });
            
            // Grafik alanını tam genişliğe çek
            try {
                var chartArea = document.querySelector('.layout__area--center');
                if (chartArea) {
                    chartArea.style.setProperty('left', '0', 'important');
                    chartArea.style.setProperty('top', '0', 'important');
                    chartArea.style.setProperty('width', '100vw', 'important');
                    chartArea.style.setProperty('height', '100vh', 'important');
                }
            } catch(e) {}
        """)
    except Exception as e:
        log.debug(f"UI gizleme hatası (devam ediliyor): {e}")


# ═══════════════════════════════════════════════════════════════
# MANUEL GİRİŞ (İLK KURULUM)
# ═══════════════════════════════════════════════════════════════

def manuel_giris_yap():
    """
    Kullanıcının TradingView'a manuel giriş yapması için
    GÖRÜNÜR bir Chrome penceresi açar.
    
    Oturum selenium_profile/ dizinine kaydedilir.
    Sonraki çalıştırmalarda bot bu profili headless modda kullanır.
    
    Kullanım:
        python3 tradingview_motoru.py
        veya
        python3 main.py --login
    """
    print()
    print("=" * 60)
    print("  🚀 TRADINGVIEW MANUEL GİRİŞ MODU")
    print("=" * 60)
    print()
    print("  1. Birazdan bir Chrome penceresi açılacak.")
    print("  2. TradingView hesabınıza giriş yapın.")
    print("     (Google, e-posta, sosyal medya — hangisini kullanıyorsanız)")
    print("  3. Giriş yaptıktan sonra bir grafik sayfası açıldığını görün.")
    print("  4. Terminale dönüp ENTER'a basın.")
    print()
    print("  ⚠️  Chrome'u elle KAPATMAYIN! ENTER'a basmanız yeterli.")
    print()
    print("=" * 60)
    print()
    
    # Profil dizinini oluştur
    os.makedirs(PROFILE_DIR, exist_ok=True)
    
    # Görünür modda Chrome aç
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--window-size=1200,800")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    
    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=None)
        print("✅ Chrome açıldı. TradingView giriş sayfasına gidiliyor...")
        print()
        
        # Giriş sayfasına git
        driver.get("https://www.tradingview.com/signin/")
        
        # Kullanıcının giriş yapmasını bekle
        input("👉 Giriş yaptıktan sonra devam etmek için ENTER'a basın...")
        
        # Giriş kontrolü
        current_url = driver.current_url
        oturum_ok = _oturum_acik_mi(driver)
        
        print()
        if oturum_ok:
            print("✅ Oturum başarıyla kaydedildi!")
            print(f"   Profil dizini: {PROFILE_DIR}")
            print()
            
            # Bir de grafik sayfasını test edelim
            print("📊 Grafik erişimi test ediliyor...")
            chart_url = settings.TRADINGVIEW_CHART_URL or DEFAULT_CHART_URL
            driver.get(chart_url)
            time.sleep(5)
            
            if "/chart/" in driver.current_url and "signin" not in driver.current_url:
                print("✅ Grafik sayfasına erişim başarılı!")
                # Test screenshot
                test_path = os.path.join("data", "test_login_screenshot.png")
                os.makedirs("data", exist_ok=True)
                driver.save_screenshot(test_path)
                print(f"📸 Test ekran görüntüsü: {test_path}")
            else:
                print("⚠️  Grafik sayfası açılamadı. URL:", driver.current_url)
        else:
            print("⚠️  Oturum algılanamadı. Lütfen tekrar deneyin.")
            print(f"   Mevcut URL: {current_url}")
        
        print()
        print("=" * 60)
        print("  Artık botu normal şekilde başlatabilirsiniz:")
        print()
        print("  nohup xvfb-run -a python3 main.py > bot_log.txt 2>&1 &")
        print("=" * 60)
        print()
        
    except Exception as e:
        print(f"\n❌ Hata: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
# DOĞRUDAN ÇALIŞTIRMA
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    manuel_giris_yap()
