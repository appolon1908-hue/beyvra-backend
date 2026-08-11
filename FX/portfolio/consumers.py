import json
import asyncio
import aiohttp
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs
from django.conf import settings
from FX.provider_credentials import required_provider_credential
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Asset
from .serializers import AssetSerializer
from django.contrib.auth import get_user_model
from trade.market_data import SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS
from trade.models import MarketCandle

User = get_user_model()


class LiveMarketDataConsumer(AsyncWebsocketConsumer):
    """Authenticated server-side relay for normalized live crypto candles."""

    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close(code=4401)
            return
        query = parse_qs(self.scope.get("query_string", b"").decode())
        self.symbol = query.get("symbol", ["BTCUSDT"])[0].upper()
        self.interval = query.get("interval", ["1m"])[0]
        if self.symbol not in SUPPORTED_SYMBOLS or self.interval not in SUPPORTED_INTERVALS:
            await self.close(code=4400)
            return
        await self.accept()
        await self.send(text_data=json.dumps({"type": "status", "status": "connecting"}))
        self.relay_task = asyncio.create_task(self.relay_market_data())

    async def disconnect(self, close_code):
        task = getattr(self, "relay_task", None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def relay_market_data(self):
        delay = 1
        while True:
            try:
                await self.stream_once()
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception:
                await self.send(text_data=json.dumps({"type": "status", "status": "disconnected", "retry_in": delay}))
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def stream_once(self):
        url = f"wss://stream.binance.com:9443/ws/{self.symbol.lower()}@kline_{self.interval}"
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20, receive_timeout=60) as upstream:
                await self.send(text_data=json.dumps({"type": "status", "status": "connected"}))
                async for message in upstream:
                    if message.type != aiohttp.WSMsgType.TEXT:
                        continue
                    payload = json.loads(message.data)
                    candle = payload.get("k")
                    if not candle:
                        continue
                    normalized = {
                        "type": "candle", "symbol": self.symbol,
                        "interval": self.interval, "closed": bool(candle["x"]),
                        "time": int(candle["t"] / 1000),
                        "open": float(candle["o"]), "high": float(candle["h"]),
                        "low": float(candle["l"]), "close": float(candle["c"]),
                        "volume": float(candle["v"]),
                    }
                    if normalized["closed"]:
                        await self.store_candle(normalized)
                    await self.send(text_data=json.dumps(normalized))

    @database_sync_to_async
    def store_candle(self, candle):
        MarketCandle.objects.update_or_create(
            provider="binance", symbol=self.symbol, interval=self.interval,
            timestamp=datetime.fromtimestamp(candle["time"], tz=timezone.utc),
            defaults={
                "open": Decimal(str(candle["open"])), "high": Decimal(str(candle["high"])),
                "low": Decimal(str(candle["low"])), "close": Decimal(str(candle["close"])),
                "volume": Decimal(str(candle["volume"])),
            },
        )


class BaseDataConsumer(AsyncWebsocketConsumer):
    """
    Classe de base pour les consommateurs WebSocket qui envoient des données périodiquement.
    """

    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close(code=4401)
            return
        await self.accept()
        self.keep_sending = True
        self.session = aiohttp.ClientSession()
        self.send_task = asyncio.create_task(self.send_data())

    async def disconnect(self, close_code):
        self.keep_sending = False
        task = getattr(self, "send_task", None)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        session = getattr(self, "session", None)
        if session and not session.closed:
            await session.close()

    async def receive(self, text_data):
        pass

    async def send_data(self):
        """ Méthode à surcharger dans les sous-classes pour envoyer des données spécifiques. """
        pass

    async def get_market_data(self, url, params=None):
        try:
            async with self.session.get(url, params=params) as response:
                return await response.json()
        except Exception:
            return {"error": "Market data is temporarily unavailable"}

class CryptoMarketDataConsumer(BaseDataConsumer):
    async def send_data(self):
        url = "https://api.polygon.io/v2/aggs/grouped/locale/global/market/crypto/2023-01-09"
        params = {"adjusted": "true", "apiKey": required_provider_credential("POLYGON_API_KEY")}
        while self.keep_sending:
            response = await self.get_market_data(url, params=params)
            await self.send(text_data=json.dumps(response))
            await asyncio.sleep(60)

class StockMarketDataConsumer(BaseDataConsumer):
    async def send_data(self):
        url = "https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/2023-01-09"
        params = {"adjusted": "true", "apiKey": required_provider_credential("POLYGON_API_KEY")}
        while self.keep_sending:
            response = await self.get_market_data(url, params=params)
            await self.send(text_data=json.dumps(response))
            await asyncio.sleep(60)

class AssetConsumer(BaseDataConsumer):
    async def send_data(self):
        user_id = self.scope["url_route"]["kwargs"]["user_id"]  # Récupérer l'ID utilisateur
        if int(user_id) != self.scope["user"].id:
            await self.close(code=4403)
            return
        user = await self.get_user(user_id)  # Obtenir l'utilisateur à partir de l'ID
        while self.keep_sending:
            assets = await self.get_assets(user)
            await self.send(text_data=json.dumps(assets))
            await asyncio.sleep(60)

    @database_sync_to_async
    def get_user(self, user_id):
        return User.objects.get(id=user_id)  # Récupérer l'utilisateur par ID

    @database_sync_to_async
    def get_assets(self, user):
        assets = Asset.objects.filter(user=user).select_related("balance", "profit_loss", "asset_type").all()
        return AssetSerializer(assets, many=True).data
    
class CurrentBalanceConsumer(BaseDataConsumer):
    async def send_data(self):
        user_id = self.scope["url_route"]["kwargs"]["user_id"]  # Récupérer l'ID utilisateur
        if int(user_id) != self.scope["user"].id:
            await self.close(code=4403)
            return
        while self.keep_sending:
            current_balance = await self.get_current_balance(user_id)
            await self.send(text_data=json.dumps({"current_balance": current_balance}))
            await asyncio.sleep(60)

    @database_sync_to_async
    def get_current_balance(self, user_id):
        assets = Asset.objects.filter(user_id=user_id).select_related("balance").all()
        total_balance = sum(asset.balance.current_balance for asset in assets if hasattr(asset, 'balance'))
        return total_balance

class ProfitLossConsumer(BaseDataConsumer):
    async def send_data(self):
        user_id = self.scope["url_route"]["kwargs"]["user_id"]  # Récupérer l'ID utilisateur
        if int(user_id) != self.scope["user"].id:
            await self.close(code=4403)
            return
        while self.keep_sending:
            profit_loss = await self.get_profit_loss(user_id)
            await self.send(text_data=json.dumps({"profit_loss": profit_loss}))
            await asyncio.sleep(60)

    @database_sync_to_async
    def get_profit_loss(self, user_id):
        assets = Asset.objects.filter(user_id=user_id).select_related("profit_loss").all()
        total_profit_loss = sum(asset.profit_loss.profit_loss for asset in assets if hasattr(asset, 'profit_loss'))
        return total_profit_loss
