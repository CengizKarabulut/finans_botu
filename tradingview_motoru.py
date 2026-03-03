"""
tradingview_motoru.py — TradingView grafik ekran görüntüsü alma modülü.
Playwright + Chromium ile otomasyon.
✅ DÜZELTİLMİŞ VERSİYON - Resource leak fix, robust waiting, retry logic eklendi
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
    """
    Output path'in dizinini oluşturur ve tam yolu döner.
    ✅ DÜZELTİLDİ: Path handling robust hale getirildi
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _format_sembol_tv(sembol: str) -> str:
    """
    Sembolü TradingView formatına çevirir.
    ✅ DÜZELTİLDİ: Daha fazla borsa desteği eklendi
    """
    sembol_upper = sembol.upper().strip()
    
    # BIST hisseleri
    if sembol_upper.endswith(".IS") or sembol_upper.endswith(".TR"):
        return f"BIST:{sembol_upper.replace('.IS', '').replace('.TR', '')}"
    
    # Londra borsası
    if sembol_upper.endswith(".L"):
        return f"LSE:{sembol_upper.replace('.L', '')}"
    
    # Frankfurt borsası
    if sembol_upper.endswith(".DE"):
        return f"XETR:{sembol_upper.replace('.DE', '')}"
    
    # Paris borsası
    if sembol_upper.endswith(".PA"):
        return f"EURONEXT:{sembol_upper.replace('.PA', '')}"
    
    # Milano borsası
    if sembol_upper.endswith(".MI"):
        return f"BIT:{sembol_upper.replace('.MI', '')}"
    
    # Amsterdam borsası
    if sembol_upper.endswith(".AS"):
        return f"EURONEXT:{sembol_upper.replace('.AS', '')}"
    
    # Hong Kong borsası
    if sembol_upper.endswith(".HK"):
        return f"HKEX:{sembol_upper.replace('.HK', '')}"
    
    # Tokyo borsası
    if sembol_upper.endswith(".T"):
        return f"TSE:{sembol_upper.replace('.T', '')}"
    
    # ABD borsaları (NASDAQ, NYSE) - otomatik tespit
    if "." not in sembol_upper and not sembol_upper.endswith((".IS", ".L", ".DE", ".PA", ".MI", ".AS", ".HK", ".T")):
        # Önce NASDAQ olarak dene, olmazsa TradingView otomatik çözer
        return f"NASDAQ:{sembol_upper}"
    
    # Diğer durumlar: olduğu gibi kullan (TradingView otomatik çözecektir)
    return sembol_upper.replace(".", ":")


async def _wait_for_chart(page: Page, timeout: int = GRAFİK_YÜKLEME_TIMEOUT) -> bool:
    """
    TradingView grafiğinin yüklenmesini bekler.
    ✅ YENİ: Element-based waiting (fragile asyncio.sleep yerine)
    """
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
            # Spinner bulunamadı veya zaten yok - bu da normal
            pass
        
        # Ekstra kısa bekleme (animasyonlar için)
        await asyncio.sleep(1)
        return True
    except PlaywrightError as e:
        log.warning(f"Grafik yükleme beklenirken timeout: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# ANA FONKSİYON: GRAFİK ÇEKME
# ═══════════════════════════════════════════════════════════════════

async def tv_grafik_cek(
    sembol: str,
    output_path: str = "logs/chart.png",
    retry_count: int = MAX_RETRY
) -> bool:
    """
    TradingView grafiğinin ekran görüntüsünü alır.
    
    Args:
        sembol: Hisse/kripto sembolü (örn: "THYAO.IS", "AAPL", "BTCUSD")
        output_path: Kaydedilecek dosya yolu
        retry_count: Maksimum retry sayısı
    
    Returns:
        bool: İşlem başarılıysa True, değilse False
    
    ✅ DÜZELTİLDİ:
    - URL trailing space fix
    - Browser context manager ile resource leak önleme
    - Element-based waiting (asyncio.sleep yerine)
    - Retry logic eklendi
    - Error handling + logging iyileştirildi
    - Type hints eklendi
    """
    output_path = _prepare_output_path(output_path)
    tv_sembol = _format_sembol_tv(sembol)
    
    # ✅ FIX: URL'deki trailing space kaldırıldı
    url = f"https://www.tradingview.com/chart/?symbol={tv_sembol}"
    
    last_error = None
    
    for attempt in range(1, retry_count + 1):
        try:
            log.info(f"📊 TradingView grafiği çekiliyor (Deneme {attempt}/{retry_count}): {url}")
            
            # ✅ FIX: async with ile proper context management - resource leak önlenir
            async with async_playwright() as p:
                browser: Browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",  # Headless mode için
                        "--disable-software-rasterizer"
                    ]
                )
                
                # ✅ FIX: Browser context ile proper cleanup
                async with browser:
                    page: Page = await browser.new_page(
                        viewport={"width": 1280, "height": 720},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                    
                    # Cookie banner'ı otomatik kapat (varsa)
                    async def _close_cookie_banner():
                        try:
                            await page.evaluate("""
                                () => {
                                    const banners = document.querySelectorAll('[class*="cookie"], [class*="consent"], [id*="cookie"]');
                                    banners.forEach(b => b.remove());
                                }
                            """)
                        except Exception:
                            pass  # Cookie banner yoksa sorun değil
                    
                    # Sayfaya git
                    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                    
                    # Cookie banner'ı kapat
                    await _close_cookie_banner()
                    
                    # ✅ FIX: Element-based waiting (fragile sleep yerine)
                    chart_loaded = await _wait_for_chart(page)
                    if not chart_loaded:
                        log.warning(f"Grafik yüklenemedi, retry denenecek...")
                        raise TimeoutError("Grafik yükleme timeout")
                    
                    # Ekran görüntüsü al
                    await page.screenshot(path=output_path, full_page=False)
                    log.info(f"✅ Grafik başarıyla kaydedildi: {output_path}")
                    return True
                    
        except PlaywrightError as e:
            last_error = e
            log.warning(f"⚠️ Playwright hatası (Deneme {attempt}/{retry_count}): {e}")
            
        except TimeoutError as e:
            last_error = e
            log.warning(f"⚠️ Timeout hatası (Deneme {attempt}/{retry_count}): {e}")
            
        except Exception as e:
            last_error = e
            log.exception(f"❌ Beklenmedik hata (Deneme {attempt}/{retry_count}): {e}")
        
        # Retry öncesi bekleme (exponential backoff)
        if attempt < retry_count:
            wait_time = RETRY_DELAY * attempt
            log.info(f"🔄 {wait_time}s sonra retry denenecek...")
            await asyncio.sleep(wait_time)
    
    # Tüm retry'ler başarısız oldu
    log.error(f"💥 TradingView grafik çekme başarısız ({retry_count} deneme): {sembol} - {last_error}")
    return False


# ═══════════════════════════════════════════════════════════════════
# OPSİYONEL: Storage State ile Login Desteği
# ═══════════════════════════════════════════════════════════════════

async def tv_grafik_cek_auth(
    sembol: str,
    output_path: str = "logs/chart.png",
    storage_state: Optional[str] = None,
    retry_count: int = MAX_RETRY
) -> bool:
    """
    TradingView grafiğini login olmuş session ile çeker.
    
    Args:
        sembol: Hisse/kripto sembolü
        output_path: Kaydedilecek dosya yolu
        storage_state: Playwright storage state JSON dosya yolu (login session)
        retry_count: Maksimum retry sayısı
    
    Returns:
        bool: İşlem başarılıysa True, değilse False
    
    ✅ YENİ: Login gerektiren premium grafikler için
    """
    output_path = _prepare_output_path(output_path)
    tv_sembol = _format_sembol_tv(sembol)
    url = f"https://www.tradingview.com/chart/?symbol={tv_sembol}"
    
    last_error = None
    
    for attempt in range(1, retry_count + 1):
        try:
            log.info(f"🔐 TradingView (auth) grafiği çekiliyor (Deneme {attempt}/{retry_count}): {url}")
            
            async with async_playwright() as p:
                browser: Browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                
                async with browser:
                    # ✅ Login session yükle (varsa)
                    context_params = {"viewport": {"width": 1280, "height": 720}}
                    if storage_state and os.path.exists(storage_state):
                        context_params["storage_state"] = storage_state
                        log.debug(f"Storage state yüklendi: {storage_state}")
                    
                    page: Page = await browser.new_page(**context_params)
                    
                    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                    
                    chart_loaded = await _wait_for_chart(page)
                    if not chart_loaded:
                        raise TimeoutError("Grafik yükleme timeout")
                    
                    await page.screenshot(path=output_path, full_page=False)
                    log.info(f"✅ Auth grafik başarıyla kaydedildi: {output_path}")
                    return True
                    
        except Exception as e:
            last_error = e
            log.exception(f"❌ Auth grafik hatası (Deneme {attempt}/{retry_count}): {e}")
            
            if attempt < retry_count:
                await asyncio.sleep(RETRY_DELAY * attempt)
    
    log.error(f"💥 Auth grafik çekme başarısız: {sembol} - {last_error}")
    return False


# ═══════════════════════════════════════════════════════════════════
# DEBUG: Test fonksiyonu
# ═══════════════════════════════════════════════════════════════════

async def test_grafik_cekme():
    """
    Geliştirici testi için basit test fonksiyonu.
    Kullanım: python -c "from tradingview_motoru import test_grafik_cekme; import asyncio; asyncio.run(test_grafik_cekme())"
    """
    test_semboller = ["THYAO.IS", "AAPL", "BTCUSD", "EURUSD"]
    
    for sembol in test_semboller:
        print(f"\n🧪 Test: {sembol}")
        path = f"logs/test_{sembol.replace('.', '_')}.png"
        success = await tv_grafik_cek(sembol, path)
        print(f"   {'✅ Başarılı' if success else '❌ Başarısız'}: {path}")
    
    print("\n🎉 Test tamamlandı!")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        sembol = sys.argv[1]
        path = sys.argv[2] if len(sys.argv) > 2 else f"logs/chart_{sembol.replace('.', '_')}.png"
        result = asyncio.run(tv_grafik_cek(sembol, path))
        print(f"{'✅ Başarılı' if result else '❌ Başarısız'}")
    else:
        asyncio.run(test_grafik_cekme())
