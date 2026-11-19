import json, os, sys, time
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from curl_cffi import requests

URL = "https://egy.voxcinemas.com/showtimes?c=city-centre-almaza"
TOKEN = os.environ["TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
FILE = "seen.json"

# 1. Load the VOX page (looks like Chrome, retries 3 times)
for attempt in range(3):
    try:
        r = requests.get(URL, impersonate="chrome", timeout=45,
                         headers={"Accept-Language": "en-US,en;q=0.9"})
        r.raise_for_status()
        break
    except Exception as e:
        print(f"Attempt {attempt + 1} failed: {e}")
        time.sleep(10)
else:
    sys.exit("Could not load VOX page.")

# 2. Collect movies
soup = BeautifulSoup(r.text, "html.parser")
movies = {}
for a in soup.select('a[href*="/movie-details/"]'):
    href = urlsplit(a["href"]).path.rstrip("/")
    name = a.get("title") or a.get_text(strip=True)
    if name and href not in movies:
        movies[href] = name

print("Found", len(movies), "movie(s)!")
if not movies:
    sys.exit("No movies read.")

# 3. Compare with what we've already seen
first_run = not os.path.exists(FILE)
seen = set() if first_run else set(json.load(open(FILE, encoding="utf-8")))

if first_run:
    seen |= movies.keys()
    print("First run: saved", len(seen), "movies, no alerts sent.")
else:
    for href in sorted(movies.keys() - seen):
        resp = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID,
                  "text": f"New Movie Released: {movies[href]}\n{urljoin(URL, href)}"},
            timeout=20,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            seen.add(href)
            print("Sent:", movies[href])
        else:
            print("Telegram error:", resp.text)

# 4. Save
with open(FILE, "w", encoding="utf-8") as f:
    json.dump(sorted(seen), f, ensure_ascii=False, indent=0)
