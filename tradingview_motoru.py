"""
tradingview_motoru.py — Selenium WebDriver ile TradingView ekran görüntüsü alır.

AKIŞ (Google Cloud SSH terminali için optimize):
  ══════════════════════════════════════════════════════════════
  Sunucuda GUI/ekran YOK. Bu yüzden cookie enjeksiyonu kullanılır:

  1. KENDİ BİLGİSAYARINIZDA:
     - Chrome'da TradingView'a giriş yapın
     - F12 → Console → şu kodu yapıştırın:
         copy(document.cookie)
     - Bu, cookie'leri panoya kopyalar.

  2. SUNUCUDA:
     - nano ~/finans_botu/data/tv_cookies.txt
     - Kopyaladığınız cookie'leri yapıştırın, kaydedin (Ctrl+O, Enter, Ctrl+X)

  3. Botu başlatın:
     - nohup xvfb-run -a --server-args="-screen 0 1920x1080x24" python3 main.py > bot_log.txt 2>&1 &

  Bot her grafik isteğinde bu cookie'leri Chrome'a enjekte eder.
  ══════════════════════════════════════════════════════════════

✅ Cookie Enjeksiyonu: Kendi PC'nizden cookie al, sunucuya yapıştır.
✅ Otomatik Sembol Değiştirme: TradingView üzerinde sembol açar.
✅ Temiz Görüntü: UI elemanlarını gizleyerek sadece grafiği yakalar.
✅ async close() — main.py shutdown ile uyumlu.
✅ Session doğrulama — Oturum açık mı kontrolü.
"""
import os
import time
import asyncio
import logging
from typing import Optional, List, Dict

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc

from config import settings

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════
# AYARLAR
# ═══════════════════════════════════════════════════════════════

PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selenium_profile")
COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tv_cookies.txt")
DEFAULT_CHART_URL = "https://www.tradingview.com/chart/"

CHART_LOAD_WAIT = 8
SYMBOL_CHANGE_WAIT = 8
UI_HIDE_WAIT = 1


# ═══════════════════════════════════════════════════════════════
# SEMBOL FORMATLAMA
# ═══════════════════════════════════════════════════════════════

def _tv_sembol_formatla(sembol: str) -> str:
    """Sembolü TradingView arama formatına çevirir."""
    s = sembol.upper().strip()

    if s.endswith(".IS"):
        return "BIST:" + s.replace(".IS", "")
    if "-" in s:
        return s.replace("-", "")
    if s.endswith("=X"):
        return s.replace("=X", "")

    _EMTIA_TV_MAP = {
        "GC=F": "COMEX:GC1!", "SI=F": "COMEX:SI1!",
        "CL=F": "NYMEX:CL1!", "BZ=F": "NYMEX:BZ1!",
        "NG=F": "NYMEX:NG1!", "HG=F": "COMEX:HG1!",
        "PL=F": "NYMEX:PL1!", "ES=F": "CME_MINI:ES1!",
        "NQ=F": "CME_MINI:NQ1!", "ZC=F": "CBOT:ZC1!",
        "ZW=F": "CBOT:ZW1!", "KC=F": "NYMEX:KC1!",
    }
    if s in _EMTIA_TV_MAP:
        return _EMTIA_TV_MAP[s]
    if s.endswith("=F"):
        return s.replace("=F", "1!")

    return s


# ═══════════════════════════════════════════════════════════════
# COOKİE YÖNETİMİ
# ═══════════════════════════════════════════════════════════════

def _cookie_dosyasi_oku() -> List[Dict]:
    """
    data/tv_cookies.txt dosyasından cookie'leri okur.
    Dosya formatı: sessionid=abc123; tv_ecuid=xyz456; ...
    """
    if not os.path.exists(COOKIE_FILE):
        log.warning(f"⚠️ Cookie dosyası bulunamadı: {COOKIE_FILE}")
        log.warning("   Çözüm:")
        log.warning("   1. PC'nizde Chrome → TradingView'a giriş yapın")
        log.warning("   2. F12 → Console → copy(document.cookie)")
        log.warning(f"   3. Sunucuda: nano {COOKIE_FILE}")
        log.warning("   4. Yapıştırıp kaydedin")
        return []

    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()

        if not raw:
            log.warning("⚠️ Cookie dosyası boş!")
            return []

        cookies = []
        for part in raw.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            idx = part.index("=")
            name = part[:idx].strip()
            value = part[idx + 1:].strip()

            if not name:
                continue

            cookies.append({
                "name": name,
                "value": value,
                "domain": ".tradingview.com",
                "path": "/",
                "secure": True,
            })

        if cookies:
            log.info(f"🍪 {len(cookies)} cookie okundu: {COOKIE_FILE}")
            onemli = {"sessionid", "tv_ecuid", "sessionid_sign"}
            bulunan = {c["name"] for c in cookies} & onemli
            if bulunan:
                log.info(f"   🔑 Kritik cookie'ler mevcut: {', '.join(bulunan)}")
            else:
                log.warning("   ⚠️ sessionid cookie'si bulunamadı!")
        else:
            log.warning("⚠️ Cookie parse edilemedi!")

        return cookies

    except Exception as e:
        log.error(f"❌ Cookie okuma hatası: {e}")
        return []


def _cookie_enjekte(driver, cookies: List[Dict]) -> bool:
    """Cookie'leri Selenium driver'a enjekte eder."""
    if not cookies:
        return False

    try:
        # Önce TradingView domain'ine git (cookie domain eşleşmesi için zorunlu)
        driver.get("https://www.tradingview.com/")
        time.sleep(3)

        driver.delete_all_cookies()

        eklenen = 0
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
                eklenen += 1
            except Exception as e:
                log.debug(f"Cookie atlandı ({cookie['name']}): {e}")

        log.info(f"🍪 {eklenen}/{len(cookies)} cookie enjekte edildi.")
        return eklenen > 0

    except Exception as e:
        log.error(f"❌ Cookie enjeksiyon hatası: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# TARAYICI YÖNETİMİ (Singleton)
# ═══════════════════════════════════════════════════════════════

class TVBrowser:
    """Singleton Chrome WebDriver yöneticisi."""
    _driver = None
    _cookies_injected = False

    @classmethod
    def get_driver(cls, headless: bool = True):
        """Chrome WebDriver döndürür (yoksa oluşturur)."""
        if cls._driver is not None:
            try:
                _ = cls._driver.current_url
                return cls._driver
            except Exception:
                log.warning("⚠️ WebDriver yanıt vermiyor, yeniden oluşturuluyor...")
                cls._force_quit()

        os.makedirs(PROFILE_DIR, exist_ok=True)

        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")

        options.add_argument(f"--user-data-dir={PROFILE_DIR}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled")

        try:
            cls._driver = uc.Chrome(options=options, version_main=None)
            cls._driver.set_page_load_timeout(60)
            cls._driver.implicitly_wait(5)
            cls._cookies_injected = False
            log.info(f"✅ Selenium WebDriver başlatıldı (headless={headless}).")
            return cls._driver
        except Exception as e:
            log.error(f"❌ WebDriver başlatılamadı: {e}")
            cls._driver = None
            return None

    @classmethod
    def _force_quit(cls):
        try:
            if cls._driver:
                cls._driver.quit()
        except Exception:
            pass
        cls._driver = None
        cls._cookies_injected = False

    @classmethod
    async def close(cls):
        """Driver'ı asenkron olarak kapat (main.py shutdown uyumlu)."""
        if cls._driver:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, cls._driver.quit)
                log.info("🔌 WebDriver kapatıldı.")
            except Exception as e:
                log.warning(f"WebDriver kapatma hatası: {e}")
            finally:
                cls._driver = None
                cls._cookies_injected = False


# ═══════════════════════════════════════════════════════════════
# OTURUM KONTROLÜ
# ═══════════════════════════════════════════════════════════════

def _oturum_acik_mi(driver) -> bool:
    """TradingView'da oturum açık mı kontrol eder."""
    try:
        current_url = driver.current_url

        if "signin" in current_url.lower():
            return False

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

        page_src = driver.page_source[:5000]
        if 'class="tv-header__link--signin"' in page_src:
            return False

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
    """TradingView üzerinden grafik ekran görüntüsü alır."""
    loop = asyncio.get_running_loop()

    try:
        driver = await loop.run_in_executor(
            None, lambda: TVBrowser.get_driver(headless=True)
        )
        if not driver:
            log.error("❌ WebDriver oluşturulamadı.")
            return False

        # Cookie enjeksiyonu (sadece ilk seferde)
        if not TVBrowser._cookies_injected:
            cookies = _cookie_dosyasi_oku()
            if cookies:
                injected = await loop.run_in_executor(
                    None, lambda: _cookie_enjekte(driver, cookies)
                )
                if injected:
                    TVBrowser._cookies_injected = True
                    log.info("🍪 Cookie'ler başarıyla enjekte edildi.")
            else:
                log.warning("⚠️ Cookie bulunamadı, oturumsuz devam ediliyor.")

        tv_symbol = _tv_sembol_formatla(sembol)
        chart_url = settings.TRADINGVIEW_CHART_URL or DEFAULT_CHART_URL

        log.info(f"📊 Grafik açılıyor: {tv_symbol}")

        await loop.run_in_executor(None, lambda: driver.get(chart_url))
        await asyncio.sleep(CHART_LOAD_WAIT)

        # Oturum kontrolü
        oturum_ok = await loop.run_in_executor(
            None, lambda: _oturum_acik_mi(driver)
        )
        if not oturum_ok:
            log.warning(
                "⚠️ TradingView oturumu açık değil!\n"
                "   Cookie'leri güncelleyin:\n"
                "   1. PC'nizde Chrome → TradingView giriş yapın\n"
                "   2. F12 → Console → copy(document.cookie)\n"
                f"   3. nano {COOKIE_FILE} → yapıştırın → kaydedin\n"
                "   4. Botu yeniden başlatın"
            )
            TVBrowser._cookies_injected = False
            return False

        # Sembol değiştir
        success = await loop.run_in_executor(
            None, lambda: _sembol_degistir(driver, tv_symbol)
        )
        if not success:
            log.warning(f"⚠️ Sembol değiştirilemedi: {tv_symbol}")

        await asyncio.sleep(SYMBOL_CHANGE_WAIT)

        # UI gizle
        await loop.run_in_executor(None, lambda: _ui_gizle(driver))
        await asyncio.sleep(UI_HIDE_WAIT)

        # Screenshot al
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        await loop.run_in_executor(
            None, lambda: driver.save_screenshot(output_path)
        )

        log.info(f"✅ Grafik kaydedildi: {output_path}")
        return True

    except Exception as e:
        log.error(f"❌ Grafik çekme hatası ({sembol}): {e}")
        TVBrowser._force_quit()
        return False


# ═══════════════════════════════════════════════════════════════
# SEMBOL DEĞİŞTİRME
# ═══════════════════════════════════════════════════════════════

def _sembol_degistir(driver, tv_symbol: str) -> bool:
    """TradingView grafik üzerinde sembolü değiştirir."""
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.ESCAPE)
        time.sleep(0.5)

        body.send_keys(tv_symbol)
        time.sleep(2)
        body.send_keys(Keys.ENTER)
        time.sleep(1)

        log.info(f"🔄 Sembol gönderildi: {tv_symbol}")
        return True

    except Exception as e:
        log.warning(f"Sembol değiştirme hatası: {e}")
        try:
            search_selectors = [
                '[data-name="symbol-search-btn"]',
                '#header-toolbar-symbol-search',
                'button[aria-label="Symbol Search"]',
            ]
            for sel in search_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, sel)
                    btn.click()
                    time.sleep(1)
                    search_input = driver.find_element(
                        By.CSS_SELECTOR,
                        'input[data-role="search"], input[type="text"]'
                    )
                    search_input.clear()
                    search_input.send_keys(tv_symbol)
                    time.sleep(2)
                    search_input.send_keys(Keys.ENTER)
                    log.info(f"🔄 Arama butonu ile gönderildi: {tv_symbol}")
                    return True
                except Exception:
                    continue
        except Exception as e2:
            log.warning(f"Alternatif yöntem de başarısız: {e2}")

    return False


# ═══════════════════════════════════════════════════════════════
# UI GİZLEME
# ═══════════════════════════════════════════════════════════════

def _ui_gizle(driver):
    """TradingView UI elemanlarını gizler."""
    try:
        driver.execute_script("""
            var selectors = [
                'header', '.tv-header', '.tv-header--mobile',
                '[data-name="drawing-toolbar"]',
                '.tv-side-toolbar',
                '.layout__area--left', '.layout__area--right',
                '.chart-controls-bar',
                '.bottom-widgetbar-content', '.tv-feed-widget',
                '.layout__area--bottom',
                '#header-toolbar-intervals', '#drawing-toolbar',
                '[data-name="right-toolbar"]'
            ];
            selectors.forEach(function(s) {
                try {
                    document.querySelectorAll(s).forEach(function(el) {
                        el.style.setProperty('display', 'none', 'important');
                    });
                } catch(e) {}
            });
            try {
                var c = document.querySelector('.layout__area--center');
                if (c) {
                    c.style.setProperty('left', '0', 'important');
                    c.style.setProperty('top', '0', 'important');
                    c.style.setProperty('width', '100vw', 'important');
                    c.style.setProperty('height', '100vh', 'important');
                }
            } catch(e) {}
        """)
    except Exception as e:
        log.debug(f"UI gizleme hatası: {e}")


# ═══════════════════════════════════════════════════════════════
# MANUEL GİRİŞ (EKRANLI ORTAMLAR İÇİN — OPSİYONEL)
# ═══════════════════════════════════════════════════════════════

def manuel_giris_yap():
    """Ekranlı ortamlarda görünür Chrome penceresi ile giriş yapar."""
    print()
    print("=" * 60)
    print("  🚀 TRADINGVIEW GİRİŞ — COOKİE YÖNTEMİ")
    print("=" * 60)
    print()
    print("  Google Cloud SSH terminali kullanıyorsanız")
    print("  aşağıdaki cookie yöntemini kullanın:")
    print()
    print("  1. PC'nizde Chrome → TradingView'a giriş yapın")
    print("  2. F12 → Console sekmesi → şunu yazın:")
    print("     copy(document.cookie)")
    print("  3. Sunucuda:")
    print(f"     nano {COOKIE_FILE}")
    print("  4. Ctrl+V ile yapıştırın → Ctrl+O → Enter → Ctrl+X")
    print("  5. Botu yeniden başlatın")
    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    manuel_giris_yap()
