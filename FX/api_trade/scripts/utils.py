import json
from pathlib import Path


def get_mock_bar_data() -> dict:
    base_dir = Path("/app")
    with open(base_dir / "api_trade/scripts/mock_bar_data.json", "r") as file:
        raw = file.read()
        bar_data = json.loads(raw)
    return bar_data
