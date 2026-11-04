
import requests
import json
import os
import sys
from urllib.parse import urljoin
from bs4 import BeautifulSoup

URL = "https://egy.voxcinemas.com/"
TOKEN = os.environ["TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
FILE = "seen.json"

# Fetch website
response = requests.get(
    URL,
    timeout=20,
    headers={"User-Agent": "Mozilla/5.0"}
)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

# Extract movies
movies = {}

for a in soup.select('a[href*="/movie-details/"]'):
    name = a.get("title") or a.get_text(strip=True)

    if name:
        movies[a["href"]] = name

print("لقيت", len(movies), "فيلم")

if not movies:
    sys.exit("مفيش افلام اتقرأت")

# Load previously seen movies
if os.path.exists(FILE):
    with open(FILE, "r", encoding="utf-8") as f:
        seen = set(json.load(f))
else:
    seen = set()

# Send Telegram notifications for new movies
for href in movies.keys() - seen:
    message = (
        f"فيلم جديد نزل: {movies[href]}\n"
        f"{urljoin(URL, href)}"
    )

    telegram_url = (
        f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    )

    response = requests.get(
        telegram_url,
        params={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=20
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        print("Telegram error:", result)
        continue

    print("تم إرسال:", movies[href])

# Save movies
with open(FILE, "w", encoding="utf-8") as f:
    json.dump(
        sorted(seen | set(movies)),
        f,
        ensure_ascii=False,
        indent=2
    )

print("تم تحديث seen.json")
