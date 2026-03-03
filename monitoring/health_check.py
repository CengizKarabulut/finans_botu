"""Health check endpoint — Docker/Kubernetes monitoring için."""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Optional
from aiohttp import web
from db import db_health_check  # Yeni fonksiyon, aşağıda tanımlanacak

log = logging.getLogger("finans_botu")

class HealthChecker:
    """Bot sağlık durumu kontrolcü."""
    
    def __init__(self, bot, dp):
        self.bot = bot
        self.dp = dp
        self.start_time = time.time()
        self.last_db_check: Optional[datetime] = None
        self.last_api_check: Optional[datetime] = None
    
    async def check_database(self) -> bool:
        """Veritabanı bağlantısını kontrol et."""
        try:
            await db_health_check()
            self.last_db_check = datetime.now()
            return True
        except Exception as e:
            log.error(f"DB health check failed: {e}")
            return False
    
    async def check_bot(self) -> bool:
        """Bot'un Telegram API'ye erişimini kontrol et."""
        try:
            await self.bot.get_me()
            return True
        except Exception as e:
            log.error(f"Bot health check failed: {e}")
            return False
    
    async def get_status(self) -> Dict:
        """Tüm sağlık kontrollerini çalıştır ve status döndür."""
        db_ok = await self.check_database()
        bot_ok = await self.check_bot()
        
        return {
            "status": "healthy" if (db_ok and bot_ok) else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": round(time.time() - self.start_time, 1),
            "checks": {
                "database": {"ok": db_ok, "last_check": self.last_db_check.isoformat() if self.last_db_check else None},
                "telegram_bot": {"ok": bot_ok},
            },
            "version": "1.2.0",  # Semver version
        }

async def health_handler(request: web.Request) -> web.Response:
    """GET /health endpoint handler."""
    checker: HealthChecker = request.app["health_checker"]
    status = await checker.get_status()
    
    http_status = 200 if status["status"] == "healthy" else 503
    return web.json_response(status, status=http_status)

async def metrics_handler(request: web.Request) -> web.Response:
    """GET /metrics endpoint — Prometheus format."""
    from .metrics import get_metrics
    metrics = get_metrics()
    
    # Prometheus text format
    lines = []
    for name, value, help_text, metric_type in metrics:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")
        lines.append(f"{name} {value}")
    
    return web.Response(text="\n".join(lines), content_type="text/plain")

async def start_health_server(host: str = "0.0.0.0", port: int = 8080):
    """Health check HTTP server'ı başlat."""
    from main import bot, dp  # Bot instance'larını import et
    
    app = web.Application()
    app["health_checker"] = HealthChecker(bot, dp)
    
    app.router.add_get("/health", health_handler)
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/", lambda r: web.json_response({"service": "finans-botu", "docs": "/health"}))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    log.info(f"🔍 Health server başlatıldı: http://{host}:{port}")
    log.info(f"   - Health: http://{host}:{port}/health")
    log.info(f"   - Metrics: http://{host}:{port}/metrics")
    
    return runner  # Caller bunu tutup cleanup yapmalı
