"""
security/circuit_breaker.py — API dayanıklılığı için Circuit Breaker deseni.
✅ YENİ ÖZELLİK - Sürekli hata alan API'leri geçici olarak devre dışı bırakır.
"""
import time
import logging
import asyncio
from typing import Dict, Optional

log = logging.getLogger("finans_botu")

class CircuitBreaker:
    """
    Circuit Breaker (Devre Kesici) Durumları:
    - CLOSED: Her şey normal, istekler iletiliyor.
    - OPEN: Hata eşiği aşıldı, istekler reddediliyor.
    - HALF_OPEN: Bekleme süresi doldu, test isteği gönderiliyor.
    """
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.failures = 0
        self.last_failure_time = 0
        self.state = 'CLOSED'
        self._lock: Optional[asyncio.Lock] = None  # Lazy init — event loop başlamadan oluşturma

    async def call(self, func, *args, **kwargs):
        """Fonksiyonu Circuit Breaker denetiminde çağırır."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = time.time()
            
            # 1. Durum Kontrolü
            if self.state == 'OPEN':
                if now - self.last_failure_time > self.recovery_timeout:
                    self.state = 'HALF_OPEN'
                    log.info(f"🔄 Circuit Breaker '{self.name}' HALF_OPEN durumuna geçti. Test ediliyor...")
                else:
                    log.warning(f"🚫 Circuit Breaker '{self.name}' OPEN durumda. İstek reddedildi.")
                    return None

            # 2. Fonksiyonu Çağır
            try:
                result = await func(*args, **kwargs)
                
                # Başarılı ise sıfırla
                self.failures = 0
                self.state = 'CLOSED'
                return result
                
            except Exception as e:
                self.failures += 1
                self.last_failure_time = now
                log.error(f"❌ Circuit Breaker '{self.name}' hata aldı ({self.failures}/{self.failure_threshold}): {e}")
                
                if self.failures >= self.failure_threshold:
                    self.state = 'OPEN'
                    log.critical(f"🚨 Circuit Breaker '{self.name}' OPEN durumuna geçti! {self.recovery_timeout}s boyunca kapalı kalacak.")
                
                return None

# Global Circuit Breaker örnekleri
cb_yfinance = CircuitBreaker("yFinance", failure_threshold=5, recovery_timeout=120)
cb_fmp = CircuitBreaker("FMP", failure_threshold=3, recovery_timeout=300)
cb_alphavantage = CircuitBreaker("AlphaVantage", failure_threshold=3, recovery_timeout=600)
