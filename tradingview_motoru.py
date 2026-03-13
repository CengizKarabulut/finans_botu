"""
tradingview_motoru.py — TradingView hesabına giriş yaparak grafik ekran görüntüsü alır.
✅ Birincil: Playwright ile TradingView oturumu açar, kayıtlı grafiği çeker.
✅ Yedek:    Playwright başarısız olursa mplfinance ile yerel mum grafiği üretir.

.env'de şunların tanımlı olması gerekir:
    TRADINGVIEW_USERNAME=kullanici_adiniz
    TRADINGVIEW_PASSWORD=sifreniz
"""
import os
import json
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv(override=True)  # os.environ'u .env değerleriyle güncelle

from config import settings  # pydantic_settings .env'i doğrudan okur

log = logging.getLogger("finans_botu")

# Kaydedilmiş TradingView oturum çerezi
_TV_COOKIE_PATH = os.path.join("data", "tv_session.json")


async def _apply_stealth(page) -> None:
    """playwright_stealth 1.x ve 2.x API'lerini destekler."""
    try:
        from playwright_stealth import stealth_async  # 1.x
        await stealth_async(page)
    except ImportError:
        try:
            from playwright_stealth import Stealth  # 2.x
            await Stealth().apply_stealth_async(page)
        except Exception:
            pass  # Stealth yoksa devam et


# ═══════════════════════════════════════════════════════════════
# SEMBOL FORMAT DÖNÜŞTÜRÜCÜLER
# ═══════════════════════════════════════════════════════════════

def _tv_sembol_formatla(sembol: str) -> str:
    """Sembolü TradingView URL parametresi formatına çevirir."""
    s = sembol.upper().strip()
    # THYAO.IS → BIST:THYAO
    if s.endswith(".IS"):
        return "BIST:" + s.replace(".IS", "")
    # BTC-USD → BINANCE:BTCUSD
    if "-" in s:
        parts = s.split("-")
        return f"BINANCE:{''.join(parts)}"
    # BTCUSD / BTCUSDT → BINANCE:BTCUSD
    for quote in ["USDT", "USD", "TRY", "BTC", "ETH", "USDC"]:
        if s.endswith(quote) and len(s) > len(quote):
            base = s[:-len(quote)]
            if len(base) >= 2:
                return f"BINANCE:{base}{quote}"
    # Global hisseler (AAPL, MSFT, TSLA…)
    return s


def _yf_sembol_formatla(sembol: str) -> str:
    """Sembolü yFinance formatına çevirir (yedek grafik için)."""
    s = sembol.upper().strip()
    if s.endswith(".IS") or "-" in s:
        return s
    for quote in ["USDT", "USD", "TRY", "BTC", "ETH", "USDC"]:
        if s.endswith(quote) and len(s) > len(quote):
            base = s[:-len(quote)]
            if len(base) >= 2:
                return f"{base}-{quote}"
    return s


# ═══════════════════════════════════════════════════════════════
# TRADİNGVİEW GİRİŞ AKIŞI
# ═══════════════════════════════════════════════════════════════

async def _tv_api_giris(username: str, password: str) -> list:
    """
    TradingView'e HTTP API üzerinden giriş yapar (headless tarayıcı tespiti yok).
    Playwright'a enjekte edilebilir cookie listesi döner.
    """
    import aiohttp

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tradingview.com/",
        "Origin": "https://www.tradingview.com",
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # Ana sayfayı ziyaret et (temel cookie'leri al)
            async with session.get("https://www.tradingview.com/") as resp:
                await resp.read()

            # Login isteği — form-encoded POST
            async with session.post(
                "https://www.tradingview.com/accounts/signin/",
                data={"username": username, "password": password, "remember": "on"},
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except Exception:
                    body = {}

                if resp.status != 200:
                    log.error(f"❌ TV API giriş başarısız: HTTP {resp.status}")
                    return []
                
                if body.get("error"):
                    error_msg = body.get("error")
                    if "captcha" in error_msg.lower():
                        log.error("❌ TradingView CAPTCHA engeline takıldı. Lütfen .env dosyasındaki TRADINGVIEW_CHART_URL'nin 'Paylaşılabilir' (Shared) olduğundan emin olun.")
                    else:
                        log.error(f"❌ TV API giriş hatası: {error_msg}")
                    return []

            # Cookie'leri Playwright formatına çevir
            pw_cookies = []
            jar_cookies = session.cookie_jar.filter_cookies("https://www.tradingview.com")
            for name, morsel in jar_cookies.items():
                pw_cookies.append({
                    "name": name,
                    "value": morsel.value,
                    "domain": ".tradingview.com",
                    "path": "/",
                })

            if pw_cookies:
                log.info(f"✅ TV API girişi başarılı. {len(pw_cookies)} cookie alındı.")
            else:
                log.warning("⚠️ TV API: Login yanıtı OK ama cookie gelmedi.")
            return pw_cookies

    except Exception as e:
        log.error(f"❌ TV API giriş exception: {e}")
        return []


async def _tv_giris_yap(page, username: str, password: str) -> bool:
    """
    TradingView'e hem HTTP API hem de Tarayıcı Formu üzerinden giriş yapmayı dener.
    """
    log.info("🔐 TradingView girişi başlatılıyor (Hibrit Yöntem)...")

    # 1. Yöntem: HTTP API ile hızlı giriş (Cookie enjeksiyonu)
    cookies = await _tv_api_giris(username, password)
    if cookies:
        # sessionid var mı kontrol et — bu kritik oturum çerezidir
        has_session = any(c["name"] in ("sessionid", "tv_ecuid") for c in cookies)
        if has_session:
            try:
                await page.context.add_cookies(cookies)
                await page.goto("https://www.tradingview.com/", wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(3000)
                if await page.query_selector('[data-name="header-user-menu-button"]'):
                    log.info("✅ API cookie ile oturum doğrulandı.")
                    return True
                log.warning("⚠️ API cookies eklendi ama header user-menu butonu görünmüyor.")
            except Exception as e:
                log.warning(f"⚠️ API çerez enjeksiyonu başarısız: {e}")

    # 2. Yöntem: Tarayıcı Formu üzerinden giriş — güncel TradingView UI (2024-2026)
    log.info("🔄 Tarayıcı formu üzerinden giriş deneniyor...")
    try:
        # Doğrudan /signin/ sayfasına git
        await page.goto("https://www.tradingview.com/signin/", wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(3000)

        # Debug: nerede olduğumuzu logla
        log.info(f"📍 Login sayfası: {page.url}")

        # ── Adım 1: "Email" sekmesini bul ve tıkla ──
        email_tab_clicked = False
        for sel in [
            'button[name="Email"]',
            '[data-name="email"]',
            'button:has-text("Email")',
            'span:has-text("Email ile devam et")',
            '.tv-signin-dialog__social--email',
            'a:has-text("Email")',
        ]:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    await page.wait_for_timeout(1500)
                    email_tab_clicked = True
                    log.info(f"✅ Email sekmesi tıklandı ({sel})")
                    break
            except Exception:
                pass

        if not email_tab_clicked:
            log.warning("⚠️ Email sekmesi bulunamadı, direkt form aranıyor...")

        # ── Adım 2: Kullanıcı adı ve şifre alanlarını doldur ──
        email_input = None
        for sel in ['input[name="username"]', 'input[autocomplete="username"]', 'input[id*="username"]', 'input[type="text"]']:
            el = await page.query_selector(sel)
            if el:
                email_input = el
                break

        pass_input = None
        for sel in ['input[name="password"]', 'input[autocomplete="current-password"]', 'input[type="password"]']:
            el = await page.query_selector(sel)
            if el:
                pass_input = el
                break

        if not email_input or not pass_input:
            # Debug screenshot al
            os.makedirs("data", exist_ok=True)
            await page.screenshot(path="data/tv_login_debug.png", full_page=True)
            log.error("❌ Giriş formu bulunamadı. Debug ekran görüntüsü: data/tv_login_debug.png")
            log.error(f"❌ Sayfa URL: {page.url}")
            return False

        await email_input.click()
        await email_input.fill(username)
        await page.wait_for_timeout(500)
        await pass_input.click()
        await pass_input.fill(password)
        await page.wait_for_timeout(500)

        # ── Adım 3: Submit ──
        submit_btn = None
        for sel in ['button[type="submit"]', 'button:has-text("Sign in")', 'button:has-text("Giriş yap")', '.tv-button--size_large[type="submit"]']:
            el = await page.query_selector(sel)
            if el:
                submit_btn = el
                break

        if not submit_btn:
            await page.screenshot(path="data/tv_login_debug.png", full_page=True)
            log.error("❌ Submit butonu bulunamadı. data/tv_login_debug.png'e bak.")
            return False

        await submit_btn.click()
        log.info("🚀 Giriş formu gönderildi, yanıt bekleniyor...")
        await page.wait_for_timeout(6000)

        # ── Adım 4: Başarı kontrolü ──
        current_url = page.url
        user_menu = await page.query_selector('[data-name="header-user-menu-button"]')
        if user_menu:
            log.info(f"✅ Tarayıcı formu ile giriş başarılı! ({current_url})")
            return True

        # Başarısız — debug screenshot
        os.makedirs("data", exist_ok=True)
        await page.screenshot(path="data/tv_login_debug.png", full_page=True)
        page_text = (await page.inner_text("body"))[:500]
        log.error(f"❌ Giriş sonrası kullanıcı menüsü yok. URL: {current_url}")
        log.error(f"❌ Sayfa içeriği (ilk 500 karakter): {page_text}")
        log.error("❌ Debug ekran görüntüsü: data/tv_login_debug.png")
        return False

    except Exception as e:
        log.error(f"❌ Tarayıcı girişi sırasında hata: {e}")
        try:
            os.makedirs("data", exist_ok=True)
            await page.screenshot(path="data/tv_login_debug.png", full_page=True)
            log.error("❌ Debug ekran görüntüsü: data/tv_login_debug.png")
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════
# BİRİNCİL: TRADINGVIEW PLAYWRIGHT YÖNTEMI
# ═══════════════════════════════════════════════════════════════

async def _sembol_degistir(page, tv_symbol: str) -> bool:
    """
    TradingView sayfasında açık grafik üzerinden sembolü değiştirir.
    Layout teması ve indikatörler korunur.
    Birden fazla yöntem sırayla denenir.
    """
    # Yöntem 1: Sembol adına tıkla → arama kutusu açılır
    symbol_selectors = [
        '[data-name="legend-series-item-title"]',
        ".chart-header-widget-logo",
        '[class*="symbolName"]',
        '[class*="symbol-description"]',
    ]
    for sel in symbol_selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                await page.wait_for_timeout(1500)
                break
        except Exception:
            continue

    # Yöntem 2: Klavye kısayolu ile arama kutusunu aç (S veya /)
    search_input = await page.query_selector(
        'input[data-role="search"], input[class*="input"][class*="search"]'
    )
    if not search_input:
        for key in ["s", "/"]:
            await page.keyboard.press(key)
            await page.wait_for_timeout(1000)
            search_input = await page.query_selector(
                'input[data-role="search"], input[class*="input"][class*="search"]'
            )
            if search_input:
                break

    if not search_input:
        log.warning("⚠️ Sembol arama kutusu bulunamadı.")
        return False

    # Arama kutusunu temizle ve sembolü yaz
    await page.evaluate("el => { el.value = ''; }", search_input)
    await search_input.type(tv_symbol, delay=80)
    await page.wait_for_timeout(2000)

    # İlk sonucu seç (Enter)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(10_000)  # Grafik + indikatör verilerinin yüklenmesi
    log.info(f"✅ Sembol değiştirildi: {tv_symbol}")
    return True


async def _grafik_tradingview(sembol: str, output_path: str) -> bool:
    """
    TradingView hesabına giriş yaparak kayıtlı grafik ekran görüntüsü alır.

    ÖNEMLİ:
    - Layout URL'si ?symbol= parametresiyle açılırsa TradingView, kaydedilmiş
      layout'ı (siyah tema, MACD, SMI) yok sayıp sıfır/açık temalı yeni grafik açar.
    - Düzeltme: Layout URL'si ÖNCE sembol olmadan açılır → tam yüklenince
      TradingView içinden sembol değiştirilir → layout teması + indikatörler korunur.
    """
    tv_user = settings.TRADINGVIEW_USERNAME
    tv_pass = settings.TRADINGVIEW_PASSWORD

    if not tv_user or not tv_pass:
        log.warning("⚠️ TRADINGVIEW_USERNAME / TRADINGVIEW_PASSWORD .env'de tanımlı değil.")
        return False

    try:
        from playwright.async_api import async_playwright

        tv_symbol = _tv_sembol_formatla(sembol)
        # Layout URL'si: ?symbol= olmadan — kaydedilmiş tema ve indikatörler korunur
        layout_url = (settings.TRADINGVIEW_CHART_URL or "https://www.tradingview.com/chart/").rstrip("/") + "/"
        log.info(f"📊 TradingView grafiği çekiliyor: {sembol} ({tv_symbol})")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            # Kaydedilmiş çerezleri yükle (önceki oturumdan)
            if os.path.exists(_TV_COOKIE_PATH):
                with open(_TV_COOKIE_PATH) as f:
                    await context.add_cookies(json.load(f))
                log.info("🍪 TradingView oturum çerezleri yüklendi.")

            page = await context.new_page()
            await _apply_stealth(page)

            # Önce giriş yap — layout private olduğu için login olmadan açılmıyor
            await page.goto("https://www.tradingview.com/", wait_until="load", timeout=60_000)
            await page.wait_for_timeout(2000)

            # Oturum açık mı kontrol et (kullanıcı adı/avatar görünüyor mu)
            oturum_acik = False
            try:
                kullanici_el = await page.query_selector(
                    '[data-name="header-user-menu-button"], '
                    '[class*="userMenuButton"], '
                    'button[aria-label*="User menu"]'
                )
                if kullanici_el:
                    oturum_acik = True
                    log.info("🍪 Mevcut oturum geçerli, yeniden giriş yapılmıyor.")
            except Exception:
                pass

            if not oturum_acik:
                log.info("🔐 Oturum yok veya geçersiz, giriş yapılıyor...")
                basarili = await _tv_giris_yap(page, tv_user, tv_pass)
                if not basarili:
                    await browser.close()
                    return False
                # Oturumu kaydet
                os.makedirs("data", exist_ok=True)
                cookies = await context.cookies()
                with open(_TV_COOKIE_PATH, "w") as f:
                    json.dump(cookies, f)
                log.info("💾 TradingView oturum çerezleri kaydedildi.")

            # Layout URL'sini ?symbol= olmadan aç → kaydedilmiş tema + indikatörler korunur
            await page.goto(layout_url, wait_until="load", timeout=60_000)
            await page.wait_for_timeout(3000)

            # Hâlâ "açamıyoruz" sayfası mı? (private layout, login başarısız)
            page_body = await page.inner_text("body")
            if "açamıyoruz" in page_body or "can't open" in page_body.lower() or "signin" in page.url:
                log.warning("⚠️ Layout açılamadı (Giriş Yapılmamış Görünüyor). Cookie siliniyor ve yeniden giriş deneniyor...")
                # Eski cookie'yi sil ve tekrar login yap
                if os.path.exists(_TV_COOKIE_PATH):
                    os.remove(_TV_COOKIE_PATH)
                
                # Önce ana sayfaya git (temiz başlangıç)
                await page.goto("https://www.tradingview.com/", wait_until="load", timeout=60_000)
                await page.wait_for_timeout(2000)
                
                basarili = await _tv_giris_yap(page, tv_user, tv_pass)
                if not basarili:
                    log.error("❌ Yeniden giriş denemesi başarısız. Lütfen TradingView kullanıcı adı ve şifrenizi kontrol edin.")
                    await browser.close()
                    return False
                
                os.makedirs("data", exist_ok=True)
                cookies = await context.cookies()
                with open(_TV_COOKIE_PATH, "w") as f:
                    json.dump(cookies, f)
                
                # Layout'a tekrar git
                log.info(f"🔄 Yeniden giriş sonrası layout açılıyor: {layout_url}")
                await page.goto(layout_url, wait_until="load", timeout=60_000)
                await page.wait_for_timeout(5000) # Daha uzun bekleme süresi
                
                # Hâlâ hata varsa, public layout URL'si gerekebilir
                page_body_after = await page.inner_text("body")
                if "açamıyoruz" in page_body_after or "can't open" in page_body_after.lower():
                    log.error("❌ Giriş yapılmasına rağmen grafik yerleşimi açılamadı. Lütfen TradingView'de grafiğinizi 'Paylaşılabilir' (Shared) yapın.")
                    await browser.close()
                    return False

            # Canvas var mı kontrol et — yoksa erişim engeli demektir, yeniden login dene
            canvas_var = False
            try:
                await page.wait_for_selector("canvas, .chart-container", timeout=15_000)
                canvas_var = True
            except Exception:
                pass

            if not canvas_var:
                try:
                    sayfa_ozet = (await page.inner_text("body"))[:300].replace("\n", " ")
                    log.warning(f"⚠️ Canvas yok. Sayfa: {sayfa_ozet}")
                except Exception:
                    pass

                log.info("🔐 Layout erişimi yok, cookie silip yeniden giriş yapılıyor...")
                if os.path.exists(_TV_COOKIE_PATH):
                    os.remove(_TV_COOKIE_PATH)

                basarili = await _tv_giris_yap(page, tv_user, tv_pass)
                if not basarili:
                    await browser.close()
                    return False

                os.makedirs("data", exist_ok=True)
                cookies = await context.cookies()
                with open(_TV_COOKIE_PATH, "w") as f:
                    json.dump(cookies, f)

                await page.goto(layout_url, wait_until="load", timeout=60_000)
                await page.wait_for_timeout(3000)

                try:
                    await page.wait_for_selector("canvas, .chart-container", timeout=20_000)
                    canvas_var = True
                except Exception:
                    log.error("❌ Giriş sonrası da canvas yok, yetki sorunu olabilir.")
                    await browser.close()
                    return False

            # Canvas yüklendi — indikatörlerin render olması için bekle
            await page.wait_for_timeout(8000)

            # Sembolü TradingView içinden değiştir (layout teması korunur)
            await _sembol_degistir(page, tv_symbol)

            # Tüm kenar çubuklarını ve araç çubuklarını gizle
            await page.evaluate("""
                [
                    'header', '.tv-header',
                    '[data-name="drawing-toolbar"]',
                    '.tv-floating-toolbar',
                    '.tv-side-toolbar',
                    '.layout__area--left',
                    '.layout__area--right',
                    '[data-name="left-toolbar"]',
                    '[data-name="right-toolbar"]',
                ].forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        el.style.display = 'none';
                    });
                });
            """)
            await page.wait_for_timeout(500)

            # Ekran görüntüsü al
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            await page.screenshot(path=output_path, full_page=False)

            await browser.close()
            log.info(f"✅ TradingView grafiği kaydedildi: {output_path}")
            return True

    except ImportError:
        log.error("❌ Playwright yüklü değil. 'pip install playwright && playwright install chromium'")
        return False
    except Exception as e:
        log.error(f"❌ TradingView Playwright hatası ({sembol}): {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# YEDEK: MPLFINANCE YEREL GRAFİK
# ═══════════════════════════════════════════════════════════════

async def _grafik_mplfinance(sembol: str, output_path: str) -> bool:
    """mplfinance + yFinance ile yerel mum grafiği oluşturur (yedek yöntem)."""
    try:
        import yfinance as yf
        import mplfinance as mpf
        import matplotlib
        matplotlib.use("Agg")

        yf_sembol = _yf_sembol_formatla(sembol)
        log.info(f"📊 mplfinance yedek grafik: {sembol} → yFinance: {yf_sembol}")

        loop = asyncio.get_running_loop()
        ticker = await loop.run_in_executor(None, lambda: yf.Ticker(yf_sembol))
        hist = await loop.run_in_executor(
            None, lambda: ticker.history(period="3mo", interval="1d")
        )

        if hist is None or hist.empty or len(hist) < 5:
            log.warning(f"⚠️ {sembol} için yeterli veri yok.")
            return False

        hist.index.name = "Date"
        hist = hist[["Open", "High", "Low", "Close", "Volume"]].dropna()

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        style = mpf.make_mpf_style(
            base_mpf_style="charles",
            gridstyle="--",
            gridcolor="#e0e0e0",
            facecolor="#ffffff",
            figcolor="#f8f8f8",
        )

        await loop.run_in_executor(None, lambda: mpf.plot(
            hist,
            type="candle",
            style=style,
            title=f"\n{sembol}  —  Son 3 Ay",
            ylabel="Fiyat",
            ylabel_lower="Hacim",
            volume=True,
            figsize=(14, 8),
            tight_layout=True,
            savefig=dict(fname=output_path, dpi=120, bbox_inches="tight"),
        ))

        log.info(f"✅ mplfinance grafiği kaydedildi: {output_path}")
        return True

    except ImportError as e:
        log.error(f"❌ mplfinance/matplotlib eksik: {e}")
        return False
    except Exception as e:
        log.error(f"❌ mplfinance hatası ({sembol}): {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# ANA FONKSİYON — Önce TV, başarısız olursa mplfinance
# ═══════════════════════════════════════════════════════════════

async def _grafik_playwright_noauth(sembol: str, output_path: str) -> bool:
    """
    Giriş yapmadan TRADINGVIEW_CHART_URL üzerinden screenshot alır.
    Kaydedilmiş public/shared layout URL'si yeterliyse bu yöntem kullanılır.
    """
    base_url = (settings.TRADINGVIEW_CHART_URL or "").strip().rstrip("/") + "/"
    if not base_url or base_url == "/":
        return False

    tv_symbol = _tv_sembol_formatla(sembol)
    # NOT: ?symbol= parametresi KULLANILMAZ — layout teması ve indikatörleri sıfırlar.
    # Layout önce sembolsüz açılır, sonra TradingView içinden sembol değiştirilir.
    log.info(f"📊 TradingView (giriş yok) grafiği çekiliyor: {sembol} → {base_url}")

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            page = await context.new_page()
            await _apply_stealth(page)
            # Layout URL'sini ?symbol= olmadan aç — kaydedilmiş tema + indikatörler korunur
            await page.goto(base_url, wait_until="load", timeout=60_000)
            await page.wait_for_timeout(3000)

            # Cookie consent / "Sign up" popup'larını kapat
            dismiss_js = """
                const cookieBtn = document.querySelector(
                    'button[id*="cookie"], button[class*="acceptAll"], ' +
                    'button[class*="accept-all"], .js-accept-all-cookies'
                );
                if (cookieBtn) cookieBtn.click();

                const closeBtn = document.querySelector(
                    'button[data-name="close"], ' +
                    '.tv-dialog__close, ' +
                    'button.close-B02UUUN3'
                );
                if (closeBtn) closeBtn.click();
            """
            await page.evaluate(dismiss_js)
            await page.wait_for_timeout(1000)

            # Canvas/grafik alanının render olmasını bekle
            try:
                await page.wait_for_selector("canvas, .chart-container", timeout=20_000)
            except Exception:
                pass

            # İndikatörlerin yüklenmesi için ek süre
            await page.wait_for_timeout(8000)

            # Sembolü TradingView içinden değiştir — layout teması + indikatörler korunur
            await _sembol_degistir(page, tv_symbol)

            # Sembol değişimi sonrası indikatör verilerinin yüklenmesi için bekle
            await page.wait_for_timeout(5000)

            # Tüm UI elementlerini gizle — temiz grafik görünümü için
            await page.evaluate("""
                [
                    '.tv-header',
                    'header',
                    '[data-name="drawing-toolbar"]',
                    '.tv-floating-toolbar',
                    '.tv-side-toolbar',
                    '.layout__area--left',
                    '.layout__area--right',
                    '.chart-controls-bar',
                    '[data-name="legend"]',
                ].forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        el.style.display = 'none';
                    });
                });
            """)
            await page.wait_for_timeout(500)

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            await page.screenshot(path=output_path, full_page=False)
            await browser.close()

            # Boş ekran kontrolü
            file_size = os.path.getsize(output_path)
            if file_size < 50_000:  # 50 KB'tan küçükse muhtemelen boş/hata sayfası
                log.warning(f"⚠️ Grafik dosyası çok küçük ({file_size} bytes), muhtemelen boş.")
                return False

            log.info(f"✅ TradingView grafiği (giriş yok) kaydedildi: {output_path} ({file_size} bytes)")
            return True

    except ImportError:
        log.error("❌ Playwright yüklü değil. 'pip install playwright && playwright install chromium'")
        return False
    except Exception as e:
        log.error(f"❌ TradingView noauth Playwright hatası ({sembol}): {e}")
        return False


async def tv_grafik_cek(sembol: str, output_path: str) -> bool:
    """
    Grafik alma akışı:
      1. TradingView Playwright girişsiz — CHART_URL varsa (paylaşılabilir link) önce bu denenir
      2. TradingView Playwright (kimlik bilgileriyle) — noauth başarısızsa ve credentials varsa
      3. mplfinance yerel grafik — son yedek

    NOT: TRADINGVIEW_CHART_URL'nin "Share chart link" ile alınan paylaşılabilir URL olması
    gerekir. Böylece login yapılmaz, TradingView güvenlik maili gelmez.
    """
    # Birincil: Girişsiz CHART_URL (paylaşılabilir link — login tetiklemez)
    if settings.TRADINGVIEW_CHART_URL:
        success = await _grafik_playwright_noauth(sembol, output_path)
        if success:
            return True
        log.warning("⚠️ TradingView noauth başarısız. CHART_URL'nin 'Share chart link' ile alınan paylaşılabilir bir URL olduğundan emin olun.")

    # İkincil: Login ile TradingView (yalnızca CHART_URL yoksa veya başarısız olduysa)
    if settings.TRADINGVIEW_USERNAME and settings.TRADINGVIEW_PASSWORD:
        log.info("🔐 Login yöntemi deneniyor (bu TradingView güvenlik maili tetikleyebilir)...")
        success = await _grafik_tradingview(sembol, output_path)
        if success:
            return True
        log.warning("⚠️ TradingView (giriş) başarısız, mplfinance yedek deneniyor...")

    # Son yedek: mplfinance
    return await _grafik_mplfinance(sembol, output_path)


# ═══════════════════════════════════════════════════════════════
# GERIYE DÖNÜK UYUMLULUK
# ═══════════════════════════════════════════════════════════════

class TVBrowser:
    """main.py'deki TVBrowser.close() çağrısı için uyumluluk katmanı."""
    @classmethod
    async def close(cls):
        pass
