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
    TradingView giriş akışını gerçekleştirir.
    Oturum başarıyla açılırsa True döner.
    """
    try:
        log.info("🔐 TradingView girişi başlatılıyor...")

        # Giriş sayfasına git
        await page.goto(
            "https://www.tradingview.com/accounts/signin/",
            wait_until="load",
            timeout=30_000,
        )
        await page.wait_for_timeout(2000)

        # "E-posta ile devam et" butonu
        try:
            email_btn = page.locator('button[name="Email"]').or_(
                page.locator('span:text("Email")').locator("..")
            )
            if await email_btn.count() > 0:
                await email_btn.first.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass  # Butona gerek olmayabilir

        # Kullanıcı adı
        await page.fill('input[name="username"]', username)
        await page.wait_for_timeout(500)

        # Şifre
        await page.fill('input[name="password"]', password)
        await page.wait_for_timeout(500)

        # Giriş butonunu tıkla
        submit = page.locator('button[type="submit"]').or_(
            page.locator('[data-overflow-tooltip-text="Sign in"]')
        )
        await submit.first.click()

        # Giriş sonucunu bekle (maks 15 sn)
        try:
            await page.wait_for_url(
                lambda url: "tradingview.com" in url and "signin" not in url,
                timeout=15_000,
            )
        except Exception:
            pass  # URL değişmeyebilir; cookie kontrolüyle devam ederiz

        await page.wait_for_timeout(3000)
        log.info("✅ TradingView girişi tamamlandı.")
        return True

    except Exception as e:
        log.error(f"❌ TradingView giriş hatası: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# BİRİNCİL: TRADINGVIEW PLAYWRIGHT YÖNTEMI
# ═══════════════════════════════════════════════════════════════

async def _grafik_tradingview(sembol: str, output_path: str) -> bool:
    """
    TradingView hesabına giriş yaparak kayıtlı grafik ekran görüntüsü alır.
    Cookie önbelleğiyle aynı oturumu yeniden kullanır.
    """
    tv_user = os.environ.get("TRADINGVIEW_USERNAME")
    tv_pass = os.environ.get("TRADINGVIEW_PASSWORD")

    if not tv_user or not tv_pass:
        log.warning("⚠️ TRADINGVIEW_USERNAME / TRADINGVIEW_PASSWORD .env'de tanımlı değil.")
        return False

    try:
        from playwright.async_api import async_playwright

        tv_symbol = _tv_sembol_formatla(sembol)
        chart_url = f"https://www.tradingview.com/chart/?symbol={tv_symbol}"
        log.info(f"📊 TradingView grafiği çekiliyor: {sembol} → {chart_url}")

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

            # Kaydedilmiş çerezleri yükle
            if os.path.exists(_TV_COOKIE_PATH):
                with open(_TV_COOKIE_PATH) as f:
                    await context.add_cookies(json.load(f))
                log.info("🍪 TradingView oturum çerezleri yüklendi.")

            page = await context.new_page()

            # Doğrudan grafiğe git
            await page.goto(chart_url, wait_until="load", timeout=60_000)
            await page.wait_for_timeout(3000)

            # Giriş gerekiyor mu?
            login_selectors = [
                'button[data-name="header-user-menu-sign-in"]',
                'a[href*="signin"]',
                'button:has-text("Sign in")',
            ]
            giris_gerekli = False
            for sel in login_selectors:
                if await page.query_selector(sel):
                    giris_gerekli = True
                    break

            if "signin" in page.url:
                giris_gerekli = True

            if giris_gerekli:
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

                # Grafiğe tekrar git
                await page.goto(chart_url, wait_until="load", timeout=60_000)
                await page.wait_for_timeout(5000)

            # Grafiğin render olmasını bekle
            try:
                await page.wait_for_selector(
                    ".chart-container, canvas.chart-gui-wrapper",
                    timeout=20_000,
                )
            except Exception:
                log.warning("⚠️ chart-container selektörü bulunamadı, ek süre bekleniyor...")

            await page.wait_for_timeout(5000)  # Render tamamlanması

            # Başlık çubuğunu gizle (daha temiz görünüm)
            await page.evaluate("""
                const header = document.querySelector('.tv-header');
                if (header) header.style.display = 'none';
                const toolbar = document.querySelector('[data-name="drawing-toolbar"]');
                if (toolbar) toolbar.style.display = 'none';
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

async def tv_grafik_cek(sembol: str, output_path: str) -> bool:
    """
    Grafik alma akışı:
      1. TradingView hesabıyla Playwright (kimlik bilgileri varsa)
      2. mplfinance yerel grafik (yedek)
    """
    # Birincil: TradingView Playwright
    if os.environ.get("TRADINGVIEW_USERNAME") and os.environ.get("TRADINGVIEW_PASSWORD"):
        success = await _grafik_tradingview(sembol, output_path)
        if success:
            return True
        log.warning("⚠️ TradingView başarısız, mplfinance yedek deneniyor...")

    # Yedek: mplfinance
    return await _grafik_mplfinance(sembol, output_path)


# ═══════════════════════════════════════════════════════════════
# GERIYE DÖNÜK UYUMLULUK
# ═══════════════════════════════════════════════════════════════

class TVBrowser:
    """main.py'deki TVBrowser.close() çağrısı için uyumluluk katmanı."""
    @classmethod
    async def close(cls):
        pass
