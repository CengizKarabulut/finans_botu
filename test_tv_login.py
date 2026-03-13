"""
test_tv_login.py — TradingView login sayfasını debug eder.
Çalıştır: python3 test_tv_login.py
data/tv_login_step*.png dosyalarını incele.
"""
import asyncio
import os

os.makedirs("data", exist_ok=True)

async def test():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Adım 1: /signin/ sayfası
        print("▶ /signin/ sayfasına gidiliyor...")
        await page.goto("https://www.tradingview.com/signin/", wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(4000)
        await page.screenshot(path="data/tv_login_step1_signin.png", full_page=True)
        print(f"📸 data/tv_login_step1_signin.png kaydedildi. URL: {page.url}")

        # Adım 2: Email sekmesi arama
        print("\n▶ Mevcut butonlar taranıyor...")
        buttons = await page.query_selector_all("button")
        for btn in buttons[:20]:
            txt = (await btn.inner_text()).strip()
            name = await btn.get_attribute("name") or ""
            data_name = await btn.get_attribute("data-name") or ""
            if txt or name or data_name:
                print(f"  BUTTON: text='{txt}' name='{name}' data-name='{data_name}'")

        # Adım 3: Email butonuna tıkla
        email_clicked = False
        for sel in [
            'button[name="Email"]',
            '[data-name="email"]',
            'button:has-text("Email")',
            'button:has-text("E-posta")',
        ]:
            el = await page.query_selector(sel)
            if el:
                print(f"\n✅ Email butonu bulundu: {sel}")
                await el.click()
                await page.wait_for_timeout(2000)
                await page.screenshot(path="data/tv_login_step2_email_clicked.png", full_page=True)
                print("📸 data/tv_login_step2_email_clicked.png kaydedildi.")
                email_clicked = True
                break

        if not email_clicked:
            print("\n⚠️ Email butonu bulunamadı!")

        # Adım 4: Form alanlarını listele
        print("\n▶ Input alanları:")
        inputs = await page.query_selector_all("input")
        for inp in inputs:
            t = await inp.get_attribute("type") or ""
            n = await inp.get_attribute("name") or ""
            ac = await inp.get_attribute("autocomplete") or ""
            ph = await inp.get_attribute("placeholder") or ""
            print(f"  INPUT: type='{t}' name='{n}' autocomplete='{ac}' placeholder='{ph}'")

        await browser.close()
        print("\n✅ Test tamamlandı. data/ klasöründeki PNG dosyalarını inceleyin.")

asyncio.run(test())
