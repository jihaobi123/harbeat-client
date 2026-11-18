"""Build lyric cue evidence on the source audio clock, in integer milliseconds."""

import math
import re
import unicodedata
from collections import defaultdict

_CLOCK = r"(\d{1,3}):([0-5]?\d)(?:\.(\d{1,3}))?"
_LINE = re.compile(r"\[" + _CLOCK + r"\]")
_WORD = re.compile(r"<" + _CLOCK + r">")
_OFFSET = re.compile(r"^\s*\[offset:([+-]?\d+)\]\s*$", re.I | re.M)
_CREDIT = re.compile(
    r"^(?:(?:作词|作曲|词曲|编曲|制作人?|演唱|原唱|和声|混音|母带|监制|录音|统筹|"
    r"策划|出品|发行|封面|版权|企划|配唱|人声|乐器|吉他|键盘|贝斯|鼓手|"
    r"lyrics?|written by|music|producer|composed by|mix(?:ed|ing)?|"
    r"master(?:ed|ing)?|copyright|op|sp|isrc)\s*[:：]|"
    r"【|©|℗|mixed by\b|mastered by\b|混音[\u3400-\u9fff]{1,8}$)",
    re.I,
)
_ONSET_TOLERANCE_MS = 650


def _milliseconds(match):
    minutes, seconds, fraction = match.groups()
    return int(minutes) * 60_000 + int(seconds) * 1000 + int((fraction or "").ljust(3, "0"))


def parse_lrc(raw, duration_ms):
    """Keep line/word start markers. A following marker is only an upper bound."""
    rows = defaultdict(set)
    for row in raw.splitlines():
        row = row.strip().lstrip("\ufeff")
        tags = []
        while tag := _LINE.match(row):
            tags.append(_milliseconds(tag))
            row = row[tag.end():]
        text = unicodedata.normalize("NFKC", _WORD.sub("", row)).strip()
        is_lyric = any(char.isalnum() for char in text) and not _CREDIT.match(text)
        if re.fullmatch(r"[「『\[（(].*[」』\]）)]", text):
            is_lyric = False
        for start in tags:
            if 0 <= start < duration_ms:
                starts = tuple(_milliseconds(w) for w in _WORD.finditer(row)) if len(tags) == 1 else ()
                if (any(not start <= w < duration_ms for w in starts)
                        or any(a > b for a, b in zip(starts, starts[1:]))):
                    starts = ()
                if is_lyric:
                    rows[start].add((text, starts))
                else:
                    rows.setdefault(start, set())
    result = []
    markers = sorted(rows)
    for start, next_mark in zip(markers, markers[1:] + [duration_ms]):
        if not rows[start]:
            continue
        text, starts = sorted(rows[start])[0]
        result.append(dict(startMs=start, nextMarkMs=next_mark, text=text,
                           wordStartsMs=[w for w in starts if w < next_mark],
                           ambiguous=len(rows[start]) > 1))
    return result


def build_lyric_timeline(raw, duration_ms, vocal_intervals):
    spans = sorted((row["start_ms"], row["end_ms"]) for row in vocal_intervals
                   if 0 <= row["start_ms"] < row["end_ms"] <= duration_ms)
    lines = parse_lrc(raw, duration_ms)
    offset = any(int(value) != 0 for value in _OFFSET.findall(raw))
    for line in lines:
        start = line["wordStartsMs"][0] if line["wordStartsMs"] else line["startMs"]
        nearby = [(lo, hi) for lo, hi in spans
                  if abs(lo - start) <= _ONSET_TOLERANCE_MS and hi > start + 120
                  and lo < line["nextMarkMs"]]
        active = [(lo, hi) for lo, hi in spans if lo <= start < hi]
        line["acousticOnsetMs"] = None
        line["vocalSpanEndMs"] = None
        if offset or line["ambiguous"]:
            line["evidence"] = "offset_requires_alignment" if offset else "ambiguous_text"
        elif len(nearby) == 1:
            lo, hi = nearby[0]
            line.update(evidence="onset_supported", acousticOnsetMs=lo, vocalSpanEndMs=hi)
        elif active or nearby:
            line["evidence"] = "vocal_present_boundary_unverified"
        else:
            line["evidence"] = "no_detected_vocal"
    first = lines[0]["startMs"] if lines else 0
    early_voice = sum(max(0, min(hi, first - _ONSET_TOLERANCE_MS) - lo) for lo, hi in spans)
    return dict(timeOrigin="master_audio_start", unit="ms", lines=lines,
                voiceBeforeFirstLineMs=early_voice)


def assess_entry(timeline, cue_ms):
    """Find a supported phrase that would already be in progress at the cue."""
    supported = [line for line in timeline["lines"] if line["evidence"] == "onset_supported"]
    for line in reversed(supported):
        onset = line["acousticOnsetMs"]
        if onset + 150 < cue_ms < min(line["vocalSpanEndMs"], line["nextMarkMs"]):
            return dict(kind="mid_line", onsetMs=onset, markMs=line["startMs"])
    for line in supported:
        onset = line["acousticOnsetMs"]
        if onset - 2000 <= cue_ms <= onset + 150:
            return dict(kind="before_line", onsetMs=onset, markMs=line["startMs"])
    return dict(kind="unverified")


def match_lrclib(record, title, artist, album, duration):
    """Require metadata for the actual version even after the provider matches it."""
    def normalized(value):
        return (" ".join(unicodedata.normalize("NFKC", value).casefold().split())
                if isinstance(value, str) else "")

    fields = ((title, "trackName"), (artist, "artistName"), (album, "albumName"))
    runtime = record.get("duration")
    synced = record.get("syncedLyrics")
    return (all(expected and normalized(expected) == normalized(record.get(key))
                for expected, key in fields)
            and isinstance(runtime, (int, float)) and math.isfinite(runtime)
            and abs(runtime - duration) <= 2 and isinstance(synced, str)
            and bool(synced.strip()) and record.get("instrumental") is not True)
