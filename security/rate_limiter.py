"""
security/rate_limiter.py — Kullanıcı bazlı istek sınırlama (Rate Limiting).
✅ MİMARİ GÜNCELLEME - Sliding Window algoritması ile hassas denetim.
"""
import time
import asyncio
import logging
from collections import defaultdict, deque
from typing import Dict, Tuple

log = logging.getLogger("finans_botu")

class SlidingWindowRateLimiter:
    """
    Sliding Window Rate Limiter.
    Belirli bir zaman penceresinde (window) maksimum istek sayısını (max_requests) denetler.
    """
    def __init__(self, max_requests: int = 10, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self.user_requests: Dict[int, deque] = defaultdict(lambda: deque())
        self._lock = asyncio.Lock()

    async def check(self, user_id: int) -> Tuple[bool, int]:
        """
        İsteğe izin verilip verilmediğini kontrol eder.
        Returns: (allowed: bool, wait_time: int)
        """
        async with self._lock:
            now = time.time()
            requests = self.user_requests[user_id]

            # Pencere dışındaki eski istekleri temizle
            while requests and requests[0] < now - self.window:
                requests.popleft()

            if len(requests) >= self.max_requests:
                # En eski isteğin pencereden çıkmasına ne kadar kaldı?
                wait_time = int(self.window - (now - requests[0]))
                log.warning(f"Rate limit aşıldı: User {user_id}, Bekleme: {wait_time}s")
                return False, max(1, wait_time)

            # Yeni isteği kaydet
            requests.append(now)
            return True, 0

# Global rate limiter örneği
# Varsayılan: 1 dakikada 10 istek
limiter = SlidingWindowRateLimiter(max_requests=10, window=60)
