import requests
import json
import os
import sys
import re
import time

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================
# Configuration
# =========================

MOVIES_URL = "https://egy.voxcinemas.com/movies/whatson"
SHOWTIMES_URL = "https://egy.voxcinemas.com/showtimes"

TOKEN = os.environ["TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

FILE = "seen.json"

# Leave empty to monitor all movies.
# Or specify movie names to monitor only certain movies.
WATCH_MOVIES = [
     "Avengers: Doomsday (Infinity Vision)",
     "Avengers: Doomsday",
]

# =========================
# Requests session
# =========================

session = requests.Session()

retry = Retry(
    total=3,
    backoff_factor=5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

adapter = HTTPAdapter(max_retries=retry)

session.mount("https://", adapter)
session.mount("http://", adapter)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_page(url):
    response = session.get(
        url,
        timeout=(15, 60),
        headers=HEADERS
    )

    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


# =========================
# Telegram
# =========================

def send_telegram(message):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    response = session.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise Exception(f"Telegram error: {result}")

    print("Telegram notification sent!")


# =========================
# Normalize movie names
# =========================

def normalize(name):

    name = name.lower().strip()

    name = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", name)

    return " ".join(name.split())


# =========================
# Get movies from VOX
# =========================

def get_movies():

    soup = get_page(MOVIES_URL)

    movies = {}

    for a in soup.select('a[href*="/movie-details/"]'):

        name = a.get("title") or a.get_text(strip=True)

        href = a.get("href")

        if name and href:

            movies[normalize(name)] = {
                "name": name,
                "url": urljoin(MOVIES_URL, href)
            }

    return movies


# =========================
# Get movies with showtimes
# =========================

def get_showtimes():

    soup = get_page(SHOWTIMES_URL)

    showtimes = {}

    headings = soup.find_all(["h2", "h3"])

    for heading in headings:

        name = heading.get_text(" ", strip=True)

        if not name:
            continue

        # Collect content until the next movie heading
        content = []

        for element in heading.find_all_next():

            if element.name in ["h2", "h3"]:
                break

            content.append(element.get_text(" ", strip=True))

        text = " ".join(content)

        # Detect cinema showtime formats
        times = re.findall(
            r"\b\d{1,2}:\d{2}\s?(?:am|pm)\b|\b\d{1,2}\s?(?:am|pm)\b",
            text,
            re.IGNORECASE
        )

        key = normalize(name)

        if key:

            showtimes[key] = {
                "name": name,
                "times": sorted(set(times))
            }

    return showtimes


# =========================
# Load previous state
# =========================

def load_state():

    if not os.path.exists(FILE):
        return None

    try:

        with open(FILE, "r", encoding="utf-8") as f:

            return json.load(f)

    except (json.JSONDecodeError, OSError):

        print("Could not read seen.json")

        return None


# =========================
# Main
# =========================

def main():

    print("Checking VOX Cinemas...")

    movies = get_movies()

    showtimes = get_showtimes()

    print("Movies found:", len(movies))
    print("Movies with showtimes:", len(showtimes))

    # Filter watched movies if configured
    if WATCH_MOVIES:

        watched_names = {
            normalize(name)
            for name in WATCH_MOVIES
        }

        movies = {
            key: value
            for key, value in movies.items()
            if key in watched_names
        }

    current_state = {}

    for key, movie in movies.items():

        matching_showtime = showtimes.get(key)

        # Check if movie has available showtimes
        available = bool(
            matching_showtime
            and matching_showtime["times"]
        )

        current_state[key] = {
            "name": movie["name"],
            "url": movie["url"],
            "available": available,
            "times": (
                matching_showtime["times"]
                if matching_showtime
                else []
            )
        }

    previous_state = load_state()

    # First run: save baseline without sending notifications
    if previous_state is None:

        print("First run: saving initial movie status.")

        with open(FILE, "w", encoding="utf-8") as f:

            json.dump(
                current_state,
                f,
                ensure_ascii=False,
                indent=2
            )

        return

    # Compare old and current movie statuses
    for key, movie in current_state.items():

        old_movie = previous_state.get(key)

        if old_movie is None:
            continue

        was_available = old_movie.get("available", False)

        is_available = movie["available"]

        # Notify when showtimes become available
        if not was_available and is_available:

            message = (
                f"🎬 مواعيد الحجز اتفتحت!\n\n"
                f"الفيلم: {movie['name']}\n\n"
                f"المواعيد: {', '.join(movie['times'])}\n\n"
                f"احجز من هنا:\n{movie['url']}"
            )

            send_telegram(message)

        # Notify when showtimes disappear
        elif was_available and not is_available:

            message = (
                f"⚠️ مواعيد الفيلم اختفت!\n\n"
                f"الفيلم: {movie['name']}\n\n"
                f"تابع الصفحة:\n{movie['url']}"
            )

            send_telegram(message)

    # Save new status
    with open(FILE, "w", encoding="utf-8") as f:

        json.dump(
            current_state,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("Monitoring completed successfully!")


if __name__ == "__main__":

    try:

        main()

    except requests.exceptions.RequestException as e:

        print("Website connection error:", e)

        sys.exit(1)

    except Exception as e:

        print("Unexpected error:", e)

        sys.exit(1)
