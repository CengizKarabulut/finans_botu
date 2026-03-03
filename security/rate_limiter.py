"""Enhanced rate limiting with Redis/DB backend."""
import time
import asyncio
import logging
from typing import Optional, Dict
from collections import defaultdict

log = logging.getLogger("finans_botu")

class MemoryRateLimiter:
    """
    In-memory rate limiter (development/single-instance).
    Production'da RedisRateLimiter kullanılmalı.
    """
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, key: str) -> bool:
        """Request izin verilir mi kontrol et."""
        async with self._lock:
            now = time.time()
            window_start = now - self.window_seconds
            
            # Eski request'leri temizle
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > window_start
            ]
            
            # Limit kontrolü
            if len(self._requests[key]) >= self.max_requests:
                return False
            
            # Yeni request'i kaydet
            self._requests[key].append(now)
            return True
    
    async def get_remaining(self, key: str) -> int:
        """Kalan request hakkını döndür."""
        async with self._lock:
            now = time.time()
            window_start = now - self.window_seconds
            current = len([ts for ts in self._requests[key] if ts > window_start])
            return max(0, self.max_requests - current)
    
    async def get_reset_time(self, key: str) -> float:
        """Window'un sıfırlanacağı zamanı döndür."""
        async with self._lock:
            if not self._requests[key]:
                return 0
            oldest = min(self._requests[key])
            return max(0, oldest + self.window_seconds - time.time())

# Global instances (config ile override edilebilir)
_default_limiter = MemoryRateLimiter(max_requests=30, window_seconds=60)  # 30/dakika
_api_limiter = MemoryRateLimiter(max_requests=100, window_seconds=60)  # API calls için

async def check_rate_limit(user_id: int, limit_type: str = "default") -> tuple[bool, dict]:
    """
    Rate limit kontrolü yap.
    
    Returns:
        (allowed: bool, info: dict with remaining/reset info)
    """
    key = f"{limit_type}:{user_id}"
    limiter = _api_limiter if limit_type == "api" else _default_limiter
    
    allowed = await limiter.is_allowed(key)
    remaining = await limiter.get_remaining(key)
    reset_in = await limiter.get_reset_time(key)
    
    return allowed, {
        "remaining": remaining,
        "reset_in_seconds": round(reset_in, 1),
        "limit": limiter.max_requests,
        "window_seconds": limiter.window_seconds,
    }

def get_rate_limit_headers(remaining: int, reset_in: float, limit: int) -> Dict[str, str]:
    """Rate limit info için HTTP-style headers döndür (opsiyonel)."""
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(int(time.time() + reset_in)),
    }
