"""
websocket_motoru.py — Gerçek zamanlı veri akışı (WebSocket).
✅ YENİ ÖZELLİK - Binance WebSocket üzerinden kripto fiyat takibi.
"""
import json
import asyncio
import logging
import aiohttp
from typing import Dict, Callable, List

log = logging.getLogger("finans_botu")

class BinanceWS:
    """Binance WebSocket istemcisi."""
    def __init__(self):
        self.url = "wss://stream.binance.com:9443/ws"
        self.callbacks: Dict[str, List[Callable]] = {}
        self.is_running = False

    async def connect(self, symbols: List[str]):
        """Belirtilen semboller için WebSocket bağlantısı kurar."""
        if not symbols: return
        
        streams = "/".join([f"{s.lower().replace('-', '')}@ticker" for s in symbols])
        full_url = f"{self.url}/{streams}"
        
        self.is_running = True
        while self.is_running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(full_url) as ws:
                        log.info(f"WebSocket bağlantısı kuruldu: {symbols}")
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                await self._handle_message(data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except Exception as e:
                log.error(f"WebSocket hatası: {e}. 10 saniye sonra tekrar denenecek...")
                await asyncio.sleep(10)

    async def _handle_message(self, data: dict):
        """Gelen veriyi işler ve ilgili callback'leri tetikler."""
        symbol = data.get('s') # Örn: BTCUSDT
        price = data.get('c')  # Güncel fiyat
        
        if symbol in self.callbacks:
            for cb in self.callbacks[symbol]:
                await cb(symbol, price)

    def add_callback(self, symbol: str, callback: Callable):
        """Bir sembol için takip fonksiyonu ekler."""
        s = symbol.upper().replace('-', '').replace('.IS', '')
        if s not in self.callbacks:
            self.callbacks[s] = []
        self.callbacks[s].append(callback)

# Global WebSocket örneği
ws_client = BinanceWS()
