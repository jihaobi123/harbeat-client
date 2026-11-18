"""Evidence-first transition planning for preprocessed tracks."""

import itertools
import math

from .transition_cues import bound_vocals, build_cues, matching_cues, section_at

POLICY_VERSION = "harbeat.transition-policy.v1"


def select_transition(candidates, fallback, *, entry_in_lyric=False, vocal_collision=False):
    """Choose only from rendered candidates. Keep the caller's approved fallback."""
    checked = [item for item in candidates if item.get("verified") is True]
    order = ["intro-beatmix", "intro-tail-handover"]
    if entry_in_lyric or vocal_collision or fallback["method"] != "dynamic-eq":
        order += ["lyric-handover-eq", "lyric-handover", "phrase-crossfade"]
    for method in order:
        if result := next((c for c in checked if c["method"] == method), None):
            return result
    return fallback


def observed_beats(track):
    grid = track.get("preprocessing", {}).get("beatGrid") or {}
    return [t / 1000 for t in grid.get("beats_ms", []) if isinstance(t, (int, float))]


def bound_vocal_peak(track, start, end):
    rms = track.get("preprocessing", {}).get("vocalRms") or {}
    asset = rms.get("asset") or {}
    if asset.get("verified_sha256") != track["provenance"]["vocalSha256"]:
        return None
    points = [p for p in rms.get("points", []) if p["start"] >= start - .005 and p["end"] <= end + .005]
    if len(points) < 2 or points[0]["start"] - start > .055 or end - points[-1]["end"] > .055:
        return None
    return max(p["rms_dbfs"] if p["rms_dbfs"] is not None else -120 for p in points)


def short_intro_plans(a, b, cue):
    """Find a short, native-speed intro before a confirmed outgoing release."""
    a_beats, b_beats = observed_beats(a), observed_beats(b)
    release, lyric = cue["aRelease"], cue["bLyric"]
    if a["duration"] - release < 3.5:
        return
    for a0 in (t for t in a_beats if release - 2.2 <= t <= release - .8):
        for b0 in (t for t in b_beats if lyric - 3.2 <= t <= lyric - 1.4):
            b_at = a0 + lyric - b0
            if not .45 <= b_at - release <= 1.65:
                continue
            if any(max(b0, lo) < min(lyric - .10, hi) for lo, hi in b["vocals"]):
                continue
            for exit_at in (t for t in a_beats if release + .27 <= t <= min(release + .85, b_at - .12)):
                observed = [t for t in b_beats if b0 + .08 < t <= b0 + exit_at - a0 + .055]
                if len(observed) < 3:
                    continue
                errors = [min(abs(x - (a0 + y - b0)) for x in a_beats) for y in observed]
                error = max(errors)
                if error <= .065:
                    yield dict(aStart=a0, aExit=exit_at, bStart=b0, rate=1,
                               maxBeatErrorMs=round(error * 1000, 1), bars=None)


def incoming_phrase(cues, b_entry):
    entries = cues['entries']
    def onset(row):
        return row.get('onsetMs', row['startMs'])

    if b_entry is not None:
        at = round(b_entry * 1000)
        for row in reversed(entries):
            if onset(row) < at < row['endMs']:
                return dict(kind='mid_line' if row['basis']=='lyric-and-vocal' else 'inside_vocal',
                            onsetMs=onset(row), markMs=row['startMs'])
        for phrase in cues['protectedPhrases']:
            if phrase['startMs'] < at < phrase['endMs']:
                return dict(kind='inside_vocal', onsetMs=phrase['startMs'], markMs=phrase['startMs'])
        near = next((row for row in entries if at <= onset(row) <= at + 4500), None)
        if near:
            return dict(kind='before_line' if near['basis']=='lyric-and-vocal' else 'before_vocal',
                        onsetMs=onset(near), markMs=near['startMs'])
    first = next((row for row in entries if onset(row) <= 45_000), None)
    return dict(kind='first_line' if first['basis']=='lyric-and-vocal' else 'first_vocal',
                onsetMs=onset(first), markMs=first['startMs']) if first else {'kind': 'unverified'}


def propose_pair(a, b, lyric_record=None, *, a_reference=None, b_entry=None, a_cues=None, b_cues=None):
    """Propose source-bound timelines for further acoustic verification."""
    result = {"schema": POLICY_VERSION, "from": a["id"], "to": b["id"],
              "status": "fallback", "candidates": []}
    spans_a, spans_b = bound_vocals(a), bound_vocals(b)
    if not spans_a or not spans_b:
        return dict(result, reason="vocal_evidence_missing")
    a_cues = a_cues if matching_cues(a_cues, a) else build_cues(a)
    b_cues = b_cues if lyric_record is None and matching_cues(b_cues, b) else build_cues(b, lyric_record)
    entry = incoming_phrase(b_cues, b_entry)
    if entry['kind'] == 'unverified':
        return dict(result, reason="incoming_vocal_unverified", entryFinding=entry)
    lyric = min(entry["markMs"], entry["onsetMs"]) / 1000
    releases = [p['endMs'] / 1000 for p in a_cues['protectedPhrases']]
    releases = [t for t in releases if a['duration'] - 30 <= t <= a['duration']] if a_reference is None else releases
    if a_reference is None:
        release = max(releases, default=0)
    else:
        nearby = [t for t in releases if a_reference - 16 <= t <= a_reference + 10]
        release = min(nearby, key=lambda t: abs(t - a_reference), default=0)
    if not release:
        return dict(result, reason="outgoing_vocal_tail_unverified")
    cue = dict(aRelease=release, bLyric=lyric)
    options = []
    for method, plans in (("intro-beatmix", matched_intro_plans(a, b, cue)),
                          ("intro-tail-handover", short_intro_plans(a, b, cue))):
        for plan in plans:
            options.append(dict(plan, method=method, verified=False, **cue))
    structure_count = len(options)
    prior = max((s["end_ms"] / 1000 for s in spans_b if s["start_ms"] / 1000 < lyric - .08),
                default=0)
    lead = min(.32, lyric - prior - .025)
    if lead >= .12 and release + .7 < a["duration"]:
        options.append(dict(method="lyric-handover-eq", verified=False, **cue,
                            aStart=release + .1 - lead, aExit=release + .92 - lead,
                            bStart=lyric - lead, overlap=.82, rate=1))
    checked, rejected = [], []
    for option in options:
        next_voice = any(release < p['startMs'] / 1000 < option['aExit'] for p in a_cues['protectedPhrases'])
        cut_inside = any(p['startMs'] < option['aExit'] * 1000 < p['endMs'] for p in a_cues['protectedPhrases'])
        if next_voice or cut_inside:
            rejected.append(dict(method=option['method'], reason='outgoing_phrase_crossed'))
            continue
        b_start = option['bStart'] * 1000
        if any(p['startMs'] < b_start < p['endMs'] for p in b_cues['protectedPhrases']):
            rejected.append(dict(method=option['method'], reason='incoming_phrase_crossed'))
            continue
        a_after = bound_vocal_peak(a, release, option["aExit"])
        b_before = bound_vocal_peak(b, option["bStart"], lyric - .13)
        if (a_after is not None and a_after > -38) or (b_before is not None and b_before > -42):
            rejected.append(dict(method=option["method"], reason="audible_vocal_residue",
                                 aAfterDbfs=a_after, bBeforeDbfs=b_before))
        else:
            sections = b_cues['sections']
            checked.append(dict(option, vocalRms=dict(aAfterDbfs=a_after, bBeforeDbfs=b_before), structure={
                'aExit': section_at(a_cues['sections'], option['aExit']),
                'aSectionExit': any(x['sectionAligned'] and abs(x['time']-option['aExit']) < .001
                                    for x in a_cues['exits']),
                'bEntry': section_at(sections, option['bStart']),
                'bVoice': section_at(sections, lyric + .08),
            }))
    checked.sort(key=lambda p: (p['method']!='intro-beatmix',
                               not p['structure']['aSectionExit'],
                               p['structure']['bEntry'] not in ('intro','inst'), -(p.get('bars') or 0)))
    return dict(result, status="candidate" if checked else "fallback", candidates=checked,
                sources={label: track["provenance"] for label, track in (("a", a), ("b", b))},
                reason=("render_verification_required" if checked else "vocal_residue"
                        if rejected else "no_safe_intro_geometry"),
                entryFinding=entry, lyricStatus=b_cues['lyricStatus'],
                structureCandidates=structure_count, rejected=rejected)

def full_bar_match(a, b):
    if not a or not b or len(a) != len(b):
        return None

    def beats(rows):
        if any(not row["valid"] or len(row["beats"]) != 4 or
               abs(row["beats"][0] - row["start"]) > .001 or
               any(x >= y for x, y in zip(row["beats"], row["beats"][1:] + [row["end"]]))
               for row in rows):
            return None
        if any(abs(x["end"] - y["start"]) > .001 for x, y in zip(rows, rows[1:])):
            return None
        return [beat for row in rows for beat in row["beats"]] + [rows[-1]["end"]]

    left, right = beats(a), beats(b)
    if left is None or right is None or len(left) != len(right):
        return None
    rate = (right[-1] - right[0]) / (left[-1] - left[0])
    if not .95 <= rate <= 1.05:
        return None
    error = max(abs(x - left[0] - (y - right[0]) / rate) for x, y in zip(left, right))
    return (float(rate), error) if error <= .065 else None


def matched_intro_plans(a, b, cue):
    def groups(track, count, near):
        rows = track["alignment"]["bars"]
        return [rows[i:i + count] for i in range(len(rows) - count + 1)
                if abs(rows[i + count - 1]["end"] - near) <= 3]

    for count in (3, 2):
        for left, right in itertools.product(groups(a, count, cue["aRelease"]),
                                            groups(b, count, cue["bLyric"])):
            timing = full_bar_match(left, right)
            if not timing:
                continue
            rate, error = timing
            a0, a_end, b0 = left[0]["start"], left[-1]["end"], right[0]["start"]
            b_at = a0 + (cue["bLyric"] - b0) / rate
            gap = b_at - cue["aRelease"]
            if not (.08 <= gap <= 2.2 and b_at <= a_end and 5 <= b_at - a0 <= 14):
                continue
            if any(max(b0, lo) < min(cue["bLyric"] - .08, hi) for lo, hi in b["vocals"]):
                continue
            yield dict(aStart=a0, aExit=a_end, bStart=b0, rate=rate,
                       maxBeatErrorMs=round(error * 1000, 1), bars=count)
