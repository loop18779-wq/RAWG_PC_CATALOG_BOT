import requests
from config import RAWG_API_KEY

r = requests.get("https://api.rawg.io/api/games", params={"key": RAWG_API_KEY, "parent_platforms": 1, "page": 1, "page_size": 3}, timeout=30)
print("HTTP:", r.status_code)
r.raise_for_status()
data = r.json()
print("Total informado por RAWG:", data.get("count"))
for game in data.get("results", []):
    print("-", game.get("name"), "|", game.get("released") or "sin fecha")
print("\nPRUEBA RAWG SUPERADA")
