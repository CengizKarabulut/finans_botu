"""
tradingview_motoru.py — TradingView grafiklerini çeker.
✅ MİMARİ GÜNCELLEME - Singleton Browser Instance, Credential Protection ve Robust Selectors.
"""
import os
import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page

log = logging.getLogger("finans_botu")

class TVBrowser:
    """Singleton Browser Instance — Kaynak tüketimini minimize eder."""
    _playwright = None
    _browser: Optional[Browser] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_browser(cls) -> Browser:
        async with cls._lock:
            if cls._browser is None:
                cls._playwright = await async_playwright().start()
                cls._browser = await cls._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                log.info("🚀 Singleton Browser başlatıldı.")
            return cls._browser

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
            await cls._playwright.stop()
            cls._browser = None
            log.info("🛑 Singleton Browser kapatıldı.")

def _tv_sembol_format(sembol: str) -> str:
    """Sembolü TradingView formatına çevirir."""
    s = sembol.upper().strip()
    # BIST Hisseleri: THYAO.IS -> BIST:THYAO
    if s.endswith(".IS"):
        return f"BIST:{s.replace('.IS', '')}"
    # Kripto: BTC-USD -> BINANCE:BTCUSDT veya CRYPTO:BTCUSD
    if "-" in s:
        base, quote = s.split("-")
        return f"BINANCE:{base}{quote}T"
    # ABD Hisseleri: AAPL -> NASDAQ:AAPL
    return s

async def tv_grafik_cek(sembol: str, output_path: str) -> bool:
    """
    TradingView'dan grafik ekran görüntüsü alır.
    ✅ GÜVENLİK: Credential'lar asla loglanmaz.
    ✅ PERFORMANS: Singleton browser kullanılır.
    """
    browser = await TVBrowser.get_browser()
    context = await browser.new_context(viewport={'width': 1280, 'height': 720})
    page = await context.new_page()
    
    try:
        tv_sembol = _tv_sembol_format(sembol)
        url = f"https://www.tradingview.com/chart/?symbol={tv_sembol}"
        
        # 1. Login (Eğer bilgiler varsa)
        tv_user = os.environ.get("TRADINGVIEW_USERNAME")
        tv_pass = os.environ.get("TRADINGVIEW_PASSWORD")
        
        if tv_user and tv_pass:
            try:
                # GÜVENLİK: Kullanıcı adı ve şifre loglanmaz.
                log.info("TradingView login deneniyor...")
                await page.goto("https://www.tradingview.com/#signin", timeout=60000)
                await page.click("span.tv-signin-dialog__social-button--email")
                await page.fill("input[name='username']", tv_user)
                await page.fill("input[name='password']", tv_pass)
                await page.click("button[type='submit']")
                await page.wait_for_timeout(3000)
            except Exception as e:
                log.warning(f"TradingView login hatası (atlanıyor): {str(e)}")
        
        # 2. Grafiğe Git
        log.info(f"📊 Grafik çekiliyor: {tv_sembol}")
        await page.goto(url, timeout=90000, wait_until="networkidle")
        
        # 3. Gereksiz elementleri gizle
        try:
            await page.evaluate("""
                () => {
                    const selectors = [
                        '.tv-dialog__close', '.is-close-button', 
                        '[data-name="header-user-menu"]', '.layout__area--left'
                    ];
                    selectors.forEach(s => {
                        const el = document.querySelector(s);
                        if (el) el.style.display = 'none';
                    });
                }
            """)
        except: pass
        
        # 4. Grafiğin yüklenmesini bekle
        await asyncio.sleep(5) 
        
        # 5. Ekran görüntüsü al
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        await page.screenshot(path=output_path)
        return True
            
    except Exception as e:
        log.error(f"❌ TradingView grafik hatası ({sembol}): {str(e)}")
        return False
    finally:
        await page.close()
        await context.close()
