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


def _normalize_cookies(raw: list) -> list:
    """
    Tarayıcı eklentilerinin (EditThisCookie, Export Cookies vb.) JSON formatını
    Playwright'ın beklediği formata dönüştürür.

    Tarayıcı formatı:  expirationDate, storeId, hostOnly, session ...
    Playwright formatı: expires, httpOnly, secure, sameSite, domain, path, name, value
    """
    sameSite_map = {
        "no_restriction": "None",
        "unspecified": "Lax",
        "lax": "Lax",
        "strict": "Strict",
        "none": "None",
    }
    pw_cookies = []
    for c in raw:
        if not c.get("name") or c.get("value") is None:
            continue
        # domain başında nokta yoksa ekle (Playwright gerektirir)
        domain = c.get("domain", ".tradingview.com")
        if domain and not domain.startswith(".") and not domain.startswith("http"):
            domain = "." + domain

        expires = c.get("expires") or c.get("expirationDate") or -1
        same_raw = str(c.get("sameSite", "Lax")).lower()
        same_site = sameSite_map.get(same_raw, "Lax")

        pw_cookies.append({
            "name": c["name"],
            "value": str(c["value"]),
            "domain": domain,
            "path": c.get("path", "/"),
            "expires": int(expires) if expires != -1 else -1,
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", True)),
            "sameSite": same_site,
        })
    return pw_cookies


def _load_tv_cookies() -> list:
    """
    tv_session.json dosyasını okur ve Playwright formatına normalize eder.
    Dosya yoksa boş liste döner.
    """
    if not os.path.exists(_TV_COOKIE_PATH):
        return []
    try:
        with open(_TV_COOKIE_PATH) as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            log.error("❌ tv_session.json geçerli bir cookie listesi değil.")
            return []
        normalized = _normalize_cookies(raw)
        session_ids = [c["name"] for c in normalized if c["name"] in ("sessionid", "tv_ecuid", "tv_sessionid")]
        if session_ids:
            log.info(f"🍪 tv_session.json yüklendi: {len(normalized)} çerez ({', '.join(session_ids)} mevcut)")
        else:
            log.warning("⚠️ tv_session.json yüklendi ama 'sessionid' / 'tv_ecuid' çerezi bulunamadı. Geçersiz dosya olabilir.")
        return normalized
    except Exception as e:
        log.error(f"❌ tv_session.json okunamadı: {e}")
        return []


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

            # Kaydedilmiş çerezleri yükle (manuel export veya önceki oturumdan)
            saved_cookies = _load_tv_cookies()
            if saved_cookies:
                await context.add_cookies(saved_cookies)

            page = await context.new_page()
            await _apply_stealth(page)

            # Ana sayfayı aç ve oturum durumunu kontrol et
            await page.goto("https://www.tradingview.com/", wait_until="load", timeout=60_000)
            await page.wait_for_timeout(2000)

            oturum_acik = False
            try:
                kullanici_el = await page.query_selector(
                    '[data-name="header-user-menu-button"], '
                    '[class*="userMenuButton"], '
                    'button[aria-label*="User menu"]'
                )
                if kullanici_el:
                    oturum_acik = True
                    log.info("🍪 Mevcut oturum geçerli, giriş atlanıyor.")
            except Exception:
                pass

            if not oturum_acik:
                # Manuel cookie dosyası varsa, form girişi deneme — yenilenmesi gerekiyor
                if saved_cookies:
                    log.error(
                        "❌ data/tv_session.json çerezleri geçersiz veya süresi dolmuş.\n"
                        "   Lütfen tarayıcınızdan TradingView'e giriş yapıp çerezleri yeniden export edin:\n"
                        "   1. Chrome'da tradingview.com'a giriş yapın\n"
                        "   2. 'EditThisCookie' eklentisiyle çerezleri JSON olarak export edin\n"
                        "   3. data/tv_session.json dosyasının içine yapıştırın\n"
                        "   4. Botu yeniden başlatın"
                    )
                    await browser.close()
                    return False

                # Cookie dosyası yok — şifre ile giriş dene
                log.info("🔐 Cookie dosyası yok, şifre ile giriş deneniyor...")
                basarili = await _tv_giris_yap(page, tv_user, tv_pass)
                if not basarili:
                    log.warning(
                        "⚠️ Şifre ile giriş başarısız (Cloudflare koruması olabilir).\n"
                        "   Kalıcı çözüm için data/tv_session.json dosyasını manuel oluşturun."
                    )
                    await browser.close()
                    return False

                # Başarılı login → çerezleri kaydet
                os.makedirs("data", exist_ok=True)
                cookies = await context.cookies()
                with open(_TV_COOKIE_PATH, "w") as f:
                    json.dump(cookies, f)
                log.info("💾 TradingView oturum çerezleri kaydedildi.")

            # Layout URL'sini aç — sembol olmadan, tema ve indikatörler korunur
            await page.goto(layout_url, wait_until="load", timeout=60_000)
            await page.wait_for_timeout(3000)

            # Erişim engeli kontrolü
            page_body = await page.inner_text("body")
            if "açamıyoruz" in page_body or "can't open" in page_body.lower() or "signin" in page.url:
                log.error(
                    "❌ Grafik layout açılamadı. Olası nedenler:\n"
                    "   • Çerezler geçersiz → data/tv_session.json'u yenileyin\n"
                    "   • Layout private → TradingView'de grafiği 'Paylaşılabilir' (Shared) yapın"
                )
                await browser.close()
                return False

            # Canvas bekleniyor
            canvas_var = False
            try:
                await page.wait_for_selector("canvas, .chart-container", timeout=15_000)
                canvas_var = True
            except Exception:
                pass

            if not canvas_var:
                try:
                    sayfa_ozet = (await page.inner_text("body"))[:300].replace("\n", " ")
                    log.error(f"❌ Canvas yüklenemedi. Sayfa içeriği: {sayfa_ozet}")
                except Exception:
                    pass
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
      1. data/tv_session.json varsa → cookie ile doğrudan giriş (Cloudflare'i atlar)
      2. Credentials (.env) varsa → API + form girişi denenir
      3. CHART_URL varsa → girişsiz paylaşılabilir link denenir
      4. mplfinance → son yedek (yerel grafik)
    """
    # Öncelikli: Manuel çerez dosyası var mı?
    cookie_var = os.path.exists(_TV_COOKIE_PATH)

    if cookie_var or (settings.TRADINGVIEW_USERNAME and settings.TRADINGVIEW_PASSWORD):
        if cookie_var:
            log.info("🍪 Manuel çerez dosyası bulundu, login formu atlanıyor...")
        else:
            log.info("🔐 Şifre ile giriş deneniyor...")
        success = await _grafik_tradingview(sembol, output_path)
        if success:
            return True
        log.warning("⚠️ TradingView (kimlik doğrulama) başarısız.")

    # İkincil: Girişsiz CHART_URL (paylaşılabilir link)
    if settings.TRADINGVIEW_CHART_URL:
        log.info("🔗 Paylaşılabilir grafik linki deneniyor...")
        success = await _grafik_playwright_noauth(sembol, output_path)
        if success:
            return True
        log.warning("⚠️ TradingView noauth başarısız.")

    # Son yedek: mplfinance
    log.info("📊 Yerel mplfinance grafiğine geçiliyor...")
    return await _grafik_mplfinance(sembol, output_path)


# ═══════════════════════════════════════════════════════════════
# GERIYE DÖNÜK UYUMLULUK
# ═══════════════════════════════════════════════════════════════

class TVBrowser:
    """main.py'deki TVBrowser.close() çağrısı için uyumluluk katmanı."""
    @classmethod
    async def close(cls):
        pass
