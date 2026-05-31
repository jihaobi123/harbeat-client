"""Patch: v3-only scoring + per-call hit-distribution logging.

Run on jetson:
    /home/mark/venvs/harbeat/bin/python /tmp/dance_style_v3_only_patch.py
"""
import re
from pathlib import Path

p = Path("/home/mark/harbeat/app/modules/dj_control/dance_style.py")
src = p.read_text(encoding="utf-8")

if "import logging" not in src:
    src = src.replace(
        "from dataclasses import dataclass\nfrom typing import Iterable",
        "import logging\nfrom dataclasses import dataclass\nfrom typing import Iterable\n\nlogger = logging.getLogger(__name__)",
        1,
    )

new_combined = (
    'def score_song_combined(song, style_key: str) -> tuple[float, str, dict[str, float]]:\n'
    '    """Return (score, source, breakdown).\n'
    '\n'
    '    v3 ONLY -- no v1 fallback. Source values:\n'
    '      "v3"             : v3 fingerprint produced score > 0\n'
    '      "no_dj"          : song has no music_features.dj -> score 0\n'
    '      "v3_bpm_reject"  : v3 hard-rejected (BPM way off band) -> score 0\n'
    '    """\n'
    '    mf = getattr(song, "music_features", None) or {}\n'
    '    dj = mf.get("dj") if isinstance(mf, dict) else None\n'
    '    if not (dj and isinstance(dj, dict)):\n'
    '        return 0.0, "no_dj", {}\n'
    '    s, breakdown = score_song_for_style_v3(dj, style_key)\n'
    '    if s > 0:\n'
    '        return s, "v3", breakdown\n'
    '    return 0.0, "v3_bpm_reject", breakdown'
)

src = re.sub(
    r"def score_song_combined\(song, style_key: str\) -> tuple\[float, str, dict\[str, float\]\]:.*?return score_song_for_style\(song, style_key\), \"v1\", \{\}",
    new_combined,
    src,
    count=1,
    flags=re.DOTALL,
)

new_rank = (
    'def rank_songs_for_style(\n'
    '    songs: Iterable,\n'
    '    style_key: str,\n'
    '    limit: int | None = None,\n'
    '    min_score: float = 0.35,\n'
    ') -> list[tuple[object, float]]:\n'
    '    scored = []\n'
    '    counts = {"v3": 0, "v3_bpm_reject": 0, "no_dj": 0, "kept": 0}\n'
    '    for s in songs:\n'
    '        score, src_, _br = score_song_combined(s, style_key)\n'
    '        counts[src_] = counts.get(src_, 0) + 1\n'
    '        if score >= min_score:\n'
    '            counts["kept"] += 1\n'
    '            scored.append((s, score))\n'
    '    scored.sort(key=lambda x: x[1], reverse=True)\n'
    '    if limit is not None:\n'
    '        scored = scored[:limit]\n'
    '    total = counts["v3"] + counts["v3_bpm_reject"] + counts["no_dj"]\n'
    '    logger.info(\n'
    '        "[dance_style.rank] style=%s min=%.2f total=%d v3=%d bpm_reject=%d no_dj=%d kept=%d",\n'
    '        style_key, min_score, total,\n'
    '        counts["v3"], counts["v3_bpm_reject"], counts["no_dj"], counts["kept"],\n'
    '    )\n'
    '    return scored'
)

src = re.sub(
    r"def rank_songs_for_style\([^)]*\) -> list\[tuple\[object, float\]\]:\n.*?return scored\n",
    new_rank + "\n",
    src,
    count=1,
    flags=re.DOTALL,
)

p.write_text(src, encoding="utf-8")
print("patch applied to", p)
