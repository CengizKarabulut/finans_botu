
import asyncio
import os
import logging
from playwright.async_api import async_playwright

log = logging.getLogger("tradingview_motoru")

async def tv_grafik_cek(sembol: str, output_path: str = "logs/chart.png") -> bool:
    """TradingView grafiğinin ekran görüntüsünü alır."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            
            # TradingView sembol URL'si (Örn: https://www.tradingview.com/chart/?symbol=NASDAQ:AAPL)
            # BIST için sembol formatı BIST:THYAO şeklinde olmalı
            tv_sembol = sembol.upper().replace(".IS", "")
            if sembol.upper().endswith(".IS"):
                tv_sembol = f"BIST:{tv_sembol}"
            
            url = f"https://www.tradingview.com/chart/?symbol={tv_sembol}"
            log.info(f"TradingView grafiği çekiliyor: {url}")
            
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Grafik yüklenene kadar bekle (biraz zaman gerekebilir)
            await asyncio.sleep(5) 
            
            # Grafiğin ekran görüntüsünü al
            await page.screenshot(path=output_path)
            await browser.close()
            return True
    except Exception as e:
        log.error(f"TradingView grafik çekme hatası ({sembol}): {e}")
        return False
