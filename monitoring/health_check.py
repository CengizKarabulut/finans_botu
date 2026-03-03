"""Health check endpoint — Docker/Kubernetes monitoring için."""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict
from aiohttp import web

log = logging.getLogger("finans_botu")

class HealthChecker:
    """Bot sağlık durumu kontrolcü."""
    
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
    
    async def check_bot(self) -> bool:
        """Bot'un Telegram API'ye erişimini kontrol et."""
        try:
            await self.bot.get_me()
            return True
        except Exception as e:
            log.error(f"Bot health check failed: {e}")
            return False
    
    async def get_status(self) -> Dict:
        """Sağlık durumu döndür."""
        bot_ok = await self.check_bot()
        
        return {
            "status": "healthy" if bot_ok else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": round(time.time() - self.start_time, 1),
            "checks": {"telegram_bot": {"ok": bot_ok}},
            "version": "1.2.0",
        }

async def health_handler(request: web.Request) -> web.Response:
    """GET /health endpoint."""
    checker: HealthChecker = request.app["health_checker"]
    status = await checker.get_status()
    http_status = 200 if status["status"] == "healthy" else 503
    return web.json_response(status, status=http_status)

async def start_health_server(host: str = "0.0.0.0", port: int = 8080, bot=None):
    """Health check HTTP server'ı başlat."""
    if bot is None:
        from main import bot
    
    app = web.Application()
    app["health_checker"] = HealthChecker(bot)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", lambda r: web.json_response({"service": "finans-botu"}))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    log.info(f"🔍 Health server: http://{host}:{port}/health")
    return runner
