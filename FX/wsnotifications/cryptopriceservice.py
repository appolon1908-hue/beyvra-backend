from abc import ABC, abstractmethod
import random


class CryptoPriceService(ABC):
    @abstractmethod
    def get_price(self, crypto: str) -> float:
        pass

class CoingeckoProvider(CryptoPriceService):
    def get_price(self, crypto: str) -> float:
        # Simulate a successful API call or failure
        if random.choice([True, False]):
            raise ConnectionError("ProviderA is unavailable")
        return {"BTC": 45000, "ETH": 3000}.get(crypto.upper(), 0.0)

class BinanceProvider(CryptoPriceService):
    def get_price(self, crypto: str) -> float:
        # Simulate a successful API call or failure
        if random.choice([True, False]):
            raise ConnectionError("ProviderB is unavailable")
        return {"BTC": 45200, "ETH": 3020}.get(crypto.upper(), 0.0)
    
class Alpaca(CryptoPriceService):
    def get_price(self, crypto: str) -> float:
        # Simulate a successful API call or failure
        if random.choice([True, False]):
            raise ConnectionError("ProviderB is unavailable")
        return {"BTC": 45200, "ETH": 3020}.get(crypto.upper(), 0.0)
    
class CoinCap(CryptoPriceService):
    def get_price(self, crypto: str) -> float:
        # Simulate a successful API call or failure
        if random.choice([True, False]):
            raise ConnectionError("ProviderB is unavailable")
        return {"BTC": 45200, "ETH": 3020}.get(crypto.upper(), 0.0)
    

class CryptoPriceServiceFactory:
    providers = {
        "provider_a": CoingeckoProvider,
        "provider_b": BinanceProvider,
        "provider_a": Alpaca,
        "provider_b": CoinCap,
    }


    @staticmethod
    def get_service(provider_name: str) -> CryptoPriceService:
        provider_class = CryptoPriceServiceFactory.providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}")
        return provider_class()

# Step 4: Client Code with Failover Logic
if __name__ == "__main__":
    factory = CryptoPriceServiceFactory()
    providers = ["provider_a", "provider_b"]

    crypto = "BTC"
    for provider_name in providers:
        try:
            service = factory.get_service(provider_name)
            price = service.get_price(crypto)
            print(f"{provider_name} provided the price: {price}")
            break  # Exit loop after successful response
        except Exception as e:
            print(f"Failed with {provider_name}: {e}")
    else:
        print("All providers failed to fetch the price.")
