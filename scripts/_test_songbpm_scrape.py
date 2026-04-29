"""Test songbpm.com scraping — find BPM and key from HTML."""
import re
from urllib.request import Request, urlopen
from urllib.parse import quote

URL_BASE = "https://songbpm.com"

def slugify(text):
    """Convert text to URL slug for songbpm.com."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text


def fetch_bpm_from_songbpm(title, artist):
    """Fetch BPM and key from songbpm.com."""
    artist_slug = slugify(artist)
    title_slug = slugify(title)
    url = f"{URL_BASE}/@{artist_slug}/{title_slug}"
    
    print(f"  URL: {url}")
    
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36",
        "Accept": "text/html",
    })
    
    try:
        with urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return None
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Error: {e}")
        return None
    
    # Pattern: "91BPM" or "91 BPM" — find the first (primary) BPM
    bpm_matches = re.findall(r'(\d+)\s*BPM', html)
    
    # Pattern: "tempo of 91" or "Tempo (BPM) 91"
    tempo_matches = re.findall(r'tempo (?:of |.*?\))?\s*(\d+)', html, re.IGNORECASE)
    
    # Pattern: "Key X" — look for musical key
    key_match = re.search(r'<strong>\s*Key\s*</strong>\s*</dt>\s*<dd[^>]*>\s*([A-G][#b]?\s*(?:major|minor))', html, re.IGNORECASE)
    if not key_match:
        key_match = re.search(r'Key\s*</?\w+>\s*([A-G][#b]?)', html, re.IGNORECASE)
    
    bpm = None
    if bpm_matches:
        bpm = int(bpm_matches[0])
    elif tempo_matches:
        bpm = int(tempo_matches[0])
    
    key = key_match.group(1).strip() if key_match else None
    
    return {"bpm": bpm, "key": key, "bpm_matches": bpm_matches, "url": url}


# Test songs
SONGS = [
    ("California Love", "2Pac"),
    ("C.R.E.A.M.", "Wu-Tang Clan"),
    ("Cheshire", "ITZY"),
    ("10 Minutes", "Lee Hyori"),
    ("ATLiens", "OutKast"),
    ("On & On", "Erykah Badu"),
    ("Deep Cover", "Dr. Dre"),
]

print("=" * 60)
print("  SongBPM.com Scraping Test")
print("=" * 60)

for title, artist in SONGS:
    print(f"\n{title} - {artist}:")
    result = fetch_bpm_from_songbpm(title, artist)
    if result and result["bpm"]:
        print(f"  BPM={result['bpm']}, key={result['key']}, all_bpms={result['bpm_matches']}")
    else:
        print(f"  NOT FOUND (result={result})")
