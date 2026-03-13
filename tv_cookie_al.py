"""
tv_cookie_al.py — TradingView oturum çerezlerini manuel giriş ile kaydeder.

Kullanım:
    python3 tv_cookie_al.py

Nasıl çalışır:
    1. Görünür bir Chromium penceresi açar
    2. TradingView giriş sayfasına gider
    3. Siz hesabınıza normal giriş yaparsınız (CAPTCHA, 2FA vb. dahil)
    4. Giriş algılanınca çerezler data/tv_session.json dosyasına kaydedilir
    5. Pencere kapanır — bot artık bu çerezleri kullanır

Gereksinim: playwright kurulu olmalı
    pip install playwright
    playwright install chromium
"""

import asyncio
import json
import os
import sys


async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ Playwright kurulu değil.")
        print("   pip install playwright && playwright install chromium")
        sys.exit(1)

    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", "tv_session.json")

    print("=" * 60)
    print("  TradingView Oturum Çerezi Kaydedici")
    print("=" * 60)
    print()
    print("1. Açılan Chromium penceresinde TradingView'e giriş yapın.")
    print("2. Giriş tamamlanınca çerezler otomatik kaydedilecek.")
    print("3. Pencere kendiliğinden kapanacak.")
    print()
    print("⏳ Tarayıcı açılıyor...")

    async with async_playwright() as p:
        # Görünür pencere — headless=False
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        context = await browser.new_context(
            viewport=None,  # Tam ekran için None
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # TradingView giriş sayfasına git
        await page.goto("https://www.tradingview.com/signin/", wait_until="domcontentloaded")

        print("✅ Tarayıcı açıldı. Lütfen giriş yapın...")
        print()

        # Giriş tamamlanana kadar bekle (en fazla 5 dakika)
        print("⌛ Giriş bekleniyor (maks. 5 dakika)...")
        giris_basarili = False

        for i in range(300):  # 300 × 1 saniye = 5 dakika
            try:
                kullanici_el = await page.query_selector(
                    '[data-name="header-user-menu-button"], '
                    '[class*="userMenuButton"], '
                    'button[aria-label*="User menu"]'
                )
                if kullanici_el:
                    giris_basarili = True
                    break
            except Exception:
                pass

            await asyncio.sleep(1)

            # Her 30 saniyede bir hatırlatma
            if i > 0 and i % 30 == 0:
                dakika = (300 - i) // 60
                saniye = (300 - i) % 60
                print(f"   ⏳ Kalan süre: {dakika}dk {saniye}sn — Lütfen giriş yapın...")

        if not giris_basarili:
            print()
            print("❌ 5 dakika içinde giriş algılanamadı. Script sonlandırıldı.")
            await browser.close()
            sys.exit(1)

        print()
        print("✅ Giriş algılandı! Çerezler kaydediliyor...")

        # Çerezleri al ve kaydet
        cookies = await context.cookies()

        # Önemli çerezleri kontrol et
        onemli = [c for c in cookies if c["name"] in ("sessionid", "tv_ecuid", "tv_sessionid")]
        if not onemli:
            print("⚠️ Uyarı: 'sessionid' çerezi bulunamadı. Giriş tam olmayabilir.")
        else:
            isimler = ", ".join(c["name"] for c in onemli)
            print(f"   🔑 Kritik çerezler alındı: {isimler}")

        with open(output_path, "w") as f:
            json.dump(cookies, f, indent=2)

        print(f"   💾 {len(cookies)} çerez kaydedildi → {output_path}")
        print()
        print("✅ İşlem tamamlandı! Pencere 3 saniye sonra kapanacak.")
        print("   Artık botu yeniden başlatabilirsiniz:")
        print("   python3 main.py")

        await asyncio.sleep(3)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
