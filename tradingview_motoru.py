"""
TradingView Motoru — Grafik Çekme
Playwright kullanarak TradingView üzerinden grafik ekran görüntüsü alır.
✅ PROFESYONEL VERSİYON - BIST sembol fix, login stabilizasyonu ve timeout iyileştirmesi.
"""
import os
import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright

log = logging.getLogger("finans_botu")

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
    """TradingView'dan grafik ekran görüntüsü alır."""
    tv_user = os.environ.get("TRADINGVIEW_USERNAME")
    tv_pass = os.environ.get("TRADINGVIEW_PASSWORD")
    
    tv_sembol = _tv_sembol_format(sembol)
    url = f"https://www.tradingview.com/chart/?symbol={tv_sembol}"
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            # Google Cloud Free Tier için düşük kaynak kullanımı
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            page = await context.new_page()
            
            # 1. Login (Eğer bilgiler varsa)
            if tv_user and tv_pass:
                try:
                    log.info("TradingView login deneniyor...")
                    await page.goto("https://www.tradingview.com/#signin", timeout=60000)
                    await page.click("span.tv-signin-dialog__social-button--email")
                    await page.fill("input[name='username']", tv_user)
                    await page.fill("input[name='password']", tv_pass)
                    await page.click("button[type='submit']")
                    await page.wait_for_timeout(3000) # Login sonrası bekleme
                except Exception as e:
                    log.warning(f"TradingView login hatası (atlanıyor): {e}")
            
            # 2. Grafiğe Git
            log.info(f"Grafik çekiliyor: {url}")
            await page.goto(url, timeout=90000, wait_until="networkidle")
            
            # Gereksiz elementleri gizle (Pop-up, reklam vb.)
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
            
            # Grafiğin yüklenmesini bekle
            await asyncio.sleep(5) 
            
            # Ekran görüntüsü al
            await page.screenshot(path=output_path)
            await browser.close()
            return True
            
        except Exception as e:
            log.error(f"TradingView grafik hatası ({sembol}): {e}")
            return False
