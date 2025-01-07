import json
import asyncio
import aiohttp
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Asset
from .serializers import AssetSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


class BaseDataConsumer(AsyncWebsocketConsumer):
    """
    Classe de base pour les consommateurs WebSocket qui envoient des données périodiquement.
    """

    async def connect(self):
        await self.accept()
        self.keep_sending = True
        self.session = aiohttp.ClientSession()
        await self.send_data()

    async def disconnect(self, close_code):
        self.keep_sending = False
        await self.session.close()

    async def receive(self, text_data):
        pass

    async def send_data(self):
        """ Méthode à surcharger dans les sous-classes pour envoyer des données spécifiques. """
        pass

    async def get_market_data(self, url):
        try:
            async with self.session.get(url) as response:
                return await response.json()
        except Exception as e:
            return {"error": str(e)}

class CryptoMarketDataConsumer(BaseDataConsumer):
    async def send_data(self):
        url = "https://api.polygon.io/v2/aggs/grouped/locale/global/market/crypto/2023-01-09?adjusted=true&apiKey=juvxg68ZjiGFZ1PlOMgCNG2CAApBqXmW"
        while self.keep_sending:
            response = await self.get_market_data(url)
            await self.send(text_data=json.dumps(response))
            await asyncio.sleep(60)

class StockMarketDataConsumer(BaseDataConsumer):
    async def send_data(self):
        url = "https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/2023-01-09?adjusted=true&apiKey=juvxg68ZjiGFZ1PlOMgCNG2CAApBqXmW"
        while self.keep_sending:
            response = await self.get_market_data(url)
            await self.send(text_data=json.dumps(response))
            await asyncio.sleep(60)

class AssetConsumer(BaseDataConsumer):
    async def send_data(self):
        user_id = self.scope["url_route"]["kwargs"]["user_id"]  # Récupérer l'ID utilisateur
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
        while self.keep_sending:
            profit_loss = await self.get_profit_loss(user_id)
            await self.send(text_data=json.dumps({"profit_loss": profit_loss}))
            await asyncio.sleep(60)

    @database_sync_to_async
    def get_profit_loss(self, user_id):
        assets = Asset.objects.filter(user_id=user_id).select_related("profit_loss").all()
        total_profit_loss = sum(asset.profit_loss.profit_loss for asset in assets if hasattr(asset, 'profit_loss'))
        return total_profit_loss
