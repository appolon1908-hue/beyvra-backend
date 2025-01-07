import requests

# Tester la route pour récupérer la liste des actifs
url_assets = "https://portfolio.ro/portfolio/assets"
response_assets = requests.get(url_assets)
data_assets = response_assets.json()
print("Assets:", data_assets)

# Tester la route pour récupérer le solde total du portefeuille
url_balance = "https://portfolio.ro/portfolio/balance"
response_balance = requests.get(url_balance)
data_balance = response_balance.json()
print("Balance:", data_balance)

# Tester la route pour récupérer le profit/perte total du portefeuille
url_profit_loss = "https://portfolio.ro/portfolio/profit-loss"
response_profit_loss = requests.get(url_profit_loss)
data_profit_loss = response_profit_loss.json()
print("Profit/Loss:", data_profit_loss)