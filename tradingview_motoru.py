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

async def _tv_giris_yap(page, username: str, password: str) -> bool:
    """
    TradingView'e Playwright tarayıcısı içinden fetch() ile giriş yapar.
    Login isteği tarayıcının kendi fingerprint/IP'sinden yapılır → oturum tutarlıdır.
    Python HTTP client (aiohttp) ile oluşturulan session yetersizdi çünkü
    TradingView, sunucu IP'sinden gelen sessionid'yi tarayıcı ortamında reddediyordu.
    """
    log.info("🔐 TradingView girişi başlatılıyor (browser fetch)...")
    try:
        # tradingview.com üzerinde değilsek önce ana sayfaya git
        if "tradingview.com" not in page.url:
            await page.goto("https://www.tradingview.com/", wait_until="load", timeout=30_000)
            await page.wait_for_timeout(2000)

        # Tarayıcı içinden fetch() ile login — credentials:'include' sayesinde
        # sessionid cookie doğrudan tarayıcının cookie jar'ına yazılır.
        # Not: TradingView /accounts/signin/ endpoint'i form-encoded body ister;
        #      application/json ile username/password alanları tanınmıyor (HTTP 400).
        result = await page.evaluate(
            """async (creds) => {
                try {
                    const body = new URLSearchParams();
                    body.append('username', creds.username);
                    body.append('password', creds.password);
                    body.append('remember', 'on');
                    const r = await fetch('https://www.tradingview.com/accounts/signin/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-Requested-With': 'XMLHttpRequest',
                            'Referer': 'https://www.tradingview.com/'
                        },
                        body: body.toString(),
                        credentials: 'include'
                    });
                    const data = await r.json().catch(() => ({}));
                    return {status: r.status, data};
                } catch(e) {
                    return {error: String(e)};
                }
            }""",
            {"username": username, "password": password},
        )

        if result.get("error"):
            log.error(f"❌ TradingView browser fetch hatası: {result['error']}")
            return False

        status = result.get("status", 0)
        data = result.get("data", {})

        if data.get("error"):
            log.error(f"❌ TradingView giriş hatası: {data['error']}")
            return False

        if not data.get("user"):
            log.error(
                f"❌ TradingView: Kullanıcı verisi yok. "
                f"HTTP {status}, Yanıt: {str(data)[:200]}"
            )
            return False

        log.info(f"✅ TradingView girişi tamamlandı: {data['user'].get('username', '?')}")
        return True

    except Exception as e:
        log.error(f"❌ TradingView giriş hatası: {e}")
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
                log.warning("⚠️ Layout açılamadı, cookie siliniyor ve yeniden giriş deneniyor...")
                # Eski cookie'yi sil ve tekrar login yap
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
                # Layout'a tekrar git
                await page.goto(layout_url, wait_until="load", timeout=60_000)
                await page.wait_for_timeout(3000)

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
    chart_url = f"{base_url}?symbol={tv_symbol}"
    log.info(f"📊 TradingView (giriş yok) grafiği çekiliyor: {sembol} → {chart_url}")

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
            # NOT: Cookie yüklenmez — login olunca hesap teması layout temasını ezer.
            # Public/shared layout URL'si giriş yapmadan doğru tema+indikatörlerle açılır.
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            page = await context.new_page()
            await page.goto(chart_url, wait_until="load", timeout=60_000)
            await page.wait_for_timeout(3000)

            # Cookie consent / "Sign up" popup'larını kapat
            dismiss_js = """
                // Cookie consent
                const cookieBtn = document.querySelector(
                    'button[id*="cookie"], button[class*="acceptAll"], ' +
                    'button[class*="accept-all"], .js-accept-all-cookies'
                );
                if (cookieBtn) cookieBtn.click();

                // "Sign in" veya "Get started" overlay'lerini kapat
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

            # İndikatörlerin (MACD, SMI vb.) yüklenmesi için ek süre
            await page.wait_for_timeout(8000)

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
      1. TradingView Playwright (kimlik bilgileriyle) — layout teması + indikatörler
      2. TradingView Playwright girişsiz — CHART_URL varsa yedek
      3. mplfinance yerel grafik — son yedek
    """
    # Birincil: Login ile TradingView (layout içinden sembol değiştirilir, tema korunur)
    if settings.TRADINGVIEW_USERNAME and settings.TRADINGVIEW_PASSWORD:
        success = await _grafik_tradingview(sembol, output_path)
        if success:
            return True
        log.warning("⚠️ TradingView (giriş) başarısız, noauth deneniyor...")

    # İkincil: Girişsiz CHART_URL
    if settings.TRADINGVIEW_CHART_URL:
        success = await _grafik_playwright_noauth(sembol, output_path)
        if success:
            return True
        log.warning("⚠️ TradingView noauth başarısız, mplfinance yedek deneniyor...")

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
