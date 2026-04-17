"""Quick test to check songbpm.com HTML structure for BPM data extraction."""
import re
import sys
from urllib.request import Request, urlopen

url = "https://songbpm.com/@2pac/california-love"
print(f"Fetching {url} ...")

req = Request(url, headers={
    "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36",
    "Accept": "text/html",
})
with urlopen(req, timeout=15) as resp:
    html = resp.read().decode("utf-8", errors="replace")

print(f"HTML length: {len(html)}")

# Look for BPM in various patterns
patterns = [
    (r'"tempo"\s*:\s*(\d+\.?\d*)', "JSON tempo"),
    (r'"bpm"\s*:\s*(\d+\.?\d*)', "JSON bpm"),
    (r'(\d+)\s*BPM', "N BPM"),
    (r'Tempo\s*\(BPM\)\s*(\d+)', "Tempo (BPM) N"),
    (r'tempo of (\d+)', "tempo of N"),
    (r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', "JSON-LD"),
]

for pattern, label in patterns:
    matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
    if matches:
        print(f"  [{label}]: {matches[:3]}")

# Also check meta tags
meta_match = re.findall(r'<meta[^>]+content="([^"]*bpm[^"]*)"', html, re.IGNORECASE)
if meta_match:
    print(f"  [meta]: {meta_match[:3]}")

# Check for data-* attributes
data_match = re.findall(r'data-[a-z]*="(\d+)"', html)
if data_match:
    print(f"  [data-attrs]: {data_match[:10]}")

# Search for "91" (expected BPM) around key contexts
for keyword in ["91", "BPM", "tempo", "key"]:
    idx = html.lower().find(keyword.lower())
    while idx > 0:
        snippet = html[max(0, idx-30):idx+30].replace("\n", " ")
        print(f"  [context '{keyword}' @{idx}]: ...{snippet}...")
        idx = html.lower().find(keyword.lower(), idx + 1)
        if idx > 0 and idx < len(html) - 1:
            # Only show first 3
            count = sum(1 for _ in re.finditer(keyword.lower(), html.lower()))
            if count > 3:
                print(f"  ... ({count} total occurrences)")
                break
