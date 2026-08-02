import requests


def main():
    """Manual smoke test; intentionally excluded from Django test discovery."""
    for label, url in (
        ("Assets", "https://portfolio.ro/portfolio/assets"),
        ("Balance", "https://portfolio.ro/portfolio/balance"),
        ("Profit/Loss", "https://portfolio.ro/portfolio/profit-loss"),
    ):
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print(f"{label}:", response.json())


if __name__ == "__main__":
    main()
