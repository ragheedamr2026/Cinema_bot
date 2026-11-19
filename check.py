import json, os, sys, time
from urllib.parse import urljoin, urlsplit, parse_qs
from bs4 import BeautifulSoup
from curl_cffi import requests

URL = "https://egy.voxcinemas.com/showtimes?c=city-centre-almaza"
CINEMA = "city-centre-almaza"
TOKEN = os.environ["TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
FILE = "seen.json"
SKIP = {"whatson", "comingsoon"}
GENERIC = {"info", "more info", "details", "more details", "book", "book now",
           "buy tickets", "tickets", "trailer", "watch trailer", "showtimes"}


def fetch(url):
    for attempt in range(3):
        try:
            r = requests.get(url, impersonate="chrome", timeout=45,
                             headers={"Accept-Language": "en-US,en;q=0.9"})
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"  attempt {attempt + 1} failed for {url}: {e}")
            time.sleep(10)
    return None


def read_movies(soup, movies):
    for a in soup.select('a[href*="/movies/"]'):
        href = urlsplit(a["href"]).path.rstrip("/")
        parts = href.split("/")
        if len(parts) != 3 or parts[1] != "movies" or parts[2] in SKIP:
            continue
        img = a.find("img")
        candidates = [a.get("title"), a.get_text(" ", strip=True),
                      img.get("alt") if img else None]
        name = next((c.strip() for c in candidates
                     if c and c.strip() and c.strip().lower() not in GENERIC), None)
        if movies.get(href) is None:
            movies[href] = name


# 1. Load today's page
soup = fetch(URL)
if soup is None:
    sys.exit("Could not load VOX page.")

movies = {}
read_movies(soup, movies)

# 2. Find all other dates listed for this cinema and read them too
dates = set()
for a in soup.select('a[href*="showtimes"]'):
    q = parse_qs(urlsplit(a["href"]).query)
    if q.get("c") == [CINEMA] and "d" in q:
        dates.add(q["d"][0])

print("Dates found:", ", ".join(sorted(dates)) or "none")
for d in sorted(dates):
    time.sleep(2)  # be gentle with the site
    page = fetch(f"https://egy.voxcinemas.com/showtimes?c={CINEMA}&d={d}")
    if page is None:
        sys.exit(f"Could not load date {d}; skipping this run to avoid false alerts.")
    read_movies(page, movies)

# Movies with no proper title found: build one from the link
for href, name in movies.items():
    if not name:
        movies[href] = href.split("/")[-1].replace("-", " ").title()

print("Found", len(movies), "movie(s)!")
for href, name in sorted(movies.items()):
    print("  ", name, "->", href)
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
                  "text": f"New Movie at VOX Almaza: {movies[href]}\n{urljoin(URL, href)}"},
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
