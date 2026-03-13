"""
tradingview_motoru.py — Selenium WebDriver ile TradingView ekran görüntüsü alır.
✅ Manuel Giriş Desteği: Kullanıcı bir kez giriş yapar, oturum kalıcı olur.
✅ Otomatik Sembol Değiştirme: Verilen sembolü grafik üzerinde otomatik açar.
✅ Temiz Görüntü: UI elemanlarını gizleyerek sadece grafiği yakalar.
"""
import os
import time
import logging
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc
from config import settings

log = logging.getLogger("finans_botu")

# Profil dizini (Oturumun kalıcı olması için)
PROFILE_DIR = os.path.join(os.getcwd(), "selenium_profile")

def _tv_sembol_formatla(sembol: str) -> str:
    """Sembolü TradingView formatına çevirir."""
    s = sembol.upper().strip()
    if s.endswith(".IS"):
        return "BIST:" + s.replace(".IS", "")
    if "-" in s:
        return s.replace("-", "")
    return s

class TVBrowser:
    _driver = None

    @classmethod
    def get_driver(cls, headless=True):
        if cls._driver is None:
            options = uc.ChromeOptions()
            if headless:
                options.add_argument("--headless")
            
            options.add_argument(f"--user-data-dir={PROFILE_DIR}")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            
            # Bot tespitini engellemek için ek ayarlar
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            try:
                cls._driver = uc.Chrome(options=options)
                log.info("✅ Selenium WebDriver (undetected) başlatıldı.")
            except Exception as e:
                log.error(f"❌ WebDriver başlatılamadı: {e}")
                return None
        return cls._driver

    @classmethod
    def close(cls):
        if cls._driver:
            cls._driver.quit()
            cls._driver = None
            log.info("🔌 WebDriver kapatıldı.")

async def tv_grafik_cek(sembol: str, output_path: str) -> bool:
    """TradingView üzerinden grafik ekran görüntüsü alır."""
    driver = TVBrowser.get_driver(headless=True)
    if not driver:
        return False

    try:
        tv_symbol = _tv_sembol_formatla(sembol)
        chart_url = settings.TRADINGVIEW_CHART_URL or "https://www.tradingview.com/chart/"
        
        log.info(f"📊 Grafik açılıyor: {tv_symbol}")
        driver.get(chart_url)
        time.sleep(5)

        # Giriş kontrolü
        if "signin" in driver.current_url or "açamıyoruz" in driver.page_source:
            log.warning("⚠️ Oturum açık değil veya grafik erişilemez durumda!")
            return False

        # Sembol değiştirme (Klavye kısayolu ile)
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(tv_symbol)
        time.sleep(1)
        body.send_keys(Keys.ENTER)
        log.info(f"🔄 Sembol gönderildi: {tv_symbol}, yüklenmesi bekleniyor...")
        time.sleep(10) # Grafik ve indikatörlerin yüklenmesi için

        # UI Elemanlarını Gizle (Temiz görüntü için)
        driver.execute_script("""
            var selectors = [
                'header', '.tv-header', '[data-name="drawing-toolbar"]',
                '.tv-side-toolbar', '.layout__area--left', '.layout__area--right',
                '.chart-controls-bar', '[data-name="legend"]'
            ];
            selectors.forEach(function(s) {
                document.querySelectorAll(s).forEach(function(el) {
                    el.style.display = 'none';
                });
            });
        """)
        time.sleep(1)

        # Ekran görüntüsü al
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        driver.save_screenshot(output_path)
        
        log.info(f"✅ Grafik kaydedildi: {output_path}")
        return True

    except Exception as e:
        log.error(f"❌ Selenium hatası ({sembol}): {e}")
        return False

def manuel_giris_yap():
    """Kullanıcının manuel giriş yapması için tarayıcıyı görünür modda açar."""
    print("\n" + "="*50)
    print("🚀 TRADINGVIEW MANUEL GİRİŞ MODU")
    print("="*50)
    print("1. Birazdan bir Chrome penceresi açılacak.")
    print("2. TradingView hesabınıza giriş yapın.")
    print("3. Giriş yaptıktan sonra terminale dönüp ENTER'a basın.")
    print("="*50 + "\n")
    
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--window-size=1200,800")
    
    driver = uc.Chrome(options=options)
    driver.get("https://www.tradingview.com/#signin")
    
    input("👉 Giriş yaptıktan sonra devam etmek için ENTER'a basın...")
    
    driver.quit()
    print("\n✅ Oturum kaydedildi. Artık botu normal şekilde başlatabilirsiniz.\n")

if __name__ == "__main__":
    # Doğrudan çalıştırılırsa manuel giriş modunu aç
    manuel_giris_yap()
