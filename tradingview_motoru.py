"""
tradingview_motoru.py — TradingView grafik ekran görüntüsü alma modülü.
Playwright + Chromium ile otomasyon.
✅ DÜZELTİLMİŞ VERSİYON - Login desteği, resource leak fix, robust waiting, retry logic eklendi
"""
import asyncio
import os
import logging
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page, Error as PlaywrightError

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════════
# AYARLAR
# ═══════════════════════════════════════════════════════════════════

# Grafik yükleme için maksimum bekleme süresi (ms)
GRAFİK_YÜKLEME_TIMEOUT = 30000  # 30 saniye

# Sayfa tamamen yüklenene kadar bekleme (ms)
PAGE_LOAD_TIMEOUT = 60000  # 60 saniye

# Retry ayarları
MAX_RETRY = 3
RETRY_DELAY = 2  # saniye

# ═══════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════

def _prepare_output_path(output_path: str) -> str:
    """Output path'in dizinini oluşturur ve tam yolu döner."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _format_sembol_tv(sembol: str) -> str:
    """Sembolü TradingView formatına çevirir."""
    sembol_upper = sembol.upper().strip()
    
    # BIST hisseleri
    if sembol_upper.endswith(".IS") or sembol_upper.endswith(".TR"):
        return f"BIST:{sembol_upper.replace('.IS', '').replace('.TR', '')}"
    
    # ABD borsaları (NASDAQ, NYSE) - otomatik tespit
    if "." not in sembol_upper:
        return f"NASDAQ:{sembol_upper}"
    
    return sembol_upper.replace(".", ":")


async def _wait_for_chart(page: Page, timeout: int = GRAFİK_YÜKLEME_TIMEOUT) -> bool:
    """TradingView grafiğinin yüklenmesini bekler."""
    try:
        # Grafik container'ını bekle
        await page.wait_for_selector(
            'div[data-name="chart-container"], .chart-page, .tv-chart-view',
            timeout=timeout,
            state="visible"
        )
        
        # Loading spinner'ın kaybolmasını bekle
        try:
            await page.wait_for_selector(
                '.tv-loading-spinner, .loading-indicator',
                timeout=5000,
                state="detached"
            )
        except PlaywrightError:
            pass
        
        await asyncio.sleep(2) # Ekstra bekleme
        return True
    except PlaywrightError as e:
        log.warning(f"Grafik yükleme beklenirken timeout: {e}")
        return False


async def _tv_login(page: Page) -> bool:
    """TradingView'a giriş yapar."""
    username = os.environ.get("TRADINGVIEW_USERNAME")
    password = os.environ.get("TRADINGVIEW_PASSWORD")
    
    if not username or not password:
        log.warning("TradingView kullanıcı adı veya şifre eksik, login atlanıyor.")
        return False
        
    try:
        log.info(f"🔐 TradingView'a giriş yapılıyor: {username}")
        # Login sayfasına git
        await page.goto("https://www.tradingview.com/#signin", wait_until="networkidle", timeout=30000)
        
        # Email ile giriş seçeneğini bul ve tıkla
        email_btn = page.locator('button[name="Email"], span:has-text("Email"), div:has-text("Email")').first
        if await email_btn.is_visible():
            await email_btn.click()
            await asyncio.sleep(1)
            
        # Kullanıcı adı ve şifre gir
        await page.fill('input[name="username"]', username)
        await page.fill('input[name="password"]', password)
        
        # Giriş yap butonuna tıkla
        await page.click('button[type="submit"]')
        
        # Girişin başarılı olduğunu doğrula (biraz bekle)
        await asyncio.sleep(5)
        log.info("✅ TradingView girişi denendi.")
        return True
    except Exception as e:
        log.error(f"❌ TradingView girişi sırasında hata: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════
# ANA FONKSİYON: GRAFİK ÇEKME
# ═══════════════════════════════════════════════════════════════════

async def tv_grafik_cek(
    sembol: str,
    output_path: str = "logs/chart.png",
    retry_count: int = MAX_RETRY
) -> bool:
    """TradingView grafiğinin ekran görüntüsünü alır."""
    output_path = _prepare_output_path(output_path)
    tv_sembol = _format_sembol_tv(sembol)
    url = f"https://www.tradingview.com/chart/?symbol={tv_sembol}"
    
    last_error = None
    
    for attempt in range(1, retry_count + 1):
        try:
            log.info(f"📊 TradingView grafiği çekiliyor (Deneme {attempt}/{retry_count}): {url}")
            
            async with async_playwright() as p:
                browser: Browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                
                async with browser:
                    page: Page = await browser.new_page(
                        viewport={"width": 1280, "height": 720},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                    
                    # Giriş yap
                    await _tv_login(page)
                    
                    # Grafiğe git
                    await page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
                    
                    # Grafik yüklenmesini bekle
                    chart_loaded = await _wait_for_chart(page)
                    if not chart_loaded:
                        raise TimeoutError("Grafik yükleme timeout")
                    
                    # Ekran görüntüsü al
                    await page.screenshot(path=output_path, full_page=False)
                    log.info(f"✅ Grafik başarıyla kaydedildi: {output_path}")
                    return True
                    
        except Exception as e:
            last_error = e
            log.warning(f"⚠️ Hata (Deneme {attempt}/{retry_count}): {e}")
            if attempt < retry_count:
                await asyncio.sleep(RETRY_DELAY * attempt)
    
    log.error(f"💥 TradingView grafik çekme başarısız: {sembol} - {last_error}")
    return False
