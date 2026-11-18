"""Propose source-relative stem curves for an already measured transition cue."""

import math

ROLES = ("drums", "bass", "other", "vocals")


def candidate_curves(plan, incoming):
    """Try preserving some intro harmony, then isolate rhythm if harmony conflicts."""
    duration = plan["aExit"] - plan["aStart"]
    release = plan["aRelease"] - plan["aStart"]
    lyric = (plan["bLyric"] - plan["bStart"]) / plan["rate"]
    if not 1 <= duration <= 16 or not .35 <= release <= duration - .25:
        return
    starts = [a for a, _ in incoming["vocals"]]
    starts += [p["start"] for p in incoming["alignment"]["phrases"]]
    begins = min((x for x in starts if plan["bStart"] < x <= plan["bLyric"]),
                 default=plan["bLyric"])
    voice = min(duration, (begins - plan["bStart"]) / plan["rate"] - .02)
    end_voice = release + .22
    if not math.isfinite(voice) or voice - .08 <= end_voice + .02:
        return
    a_voice = [[0, 1], [release, 1], [end_voice, 0], [duration, 0]]
    b_voice = [[0, 0], [voice - .08, 0], [voice, 1]]
    if voice < duration:
        b_voice.append([duration, 1])
    tone_switch = release + .08
    pitch_takeover = min(lyric, duration)
    if pitch_takeover - tone_switch < .05:
        return
    for switch in dict.fromkeys((min(1.5, .23 * duration, release - .1), .5 * release)):
        for lead in (.12, 0):
            if switch < .18 or switch + .12 >= tone_switch:
                continue
            a = {"drums": [[0, 1], [switch-.18, 1], [switch, 0], [duration, 0]],
                 "vocals": a_voice}
            if switch == .18:
                a["drums"].pop(1)
            b = {"drums": [[0, 0], [switch, 0], [switch+.12, .48],
                           [release, .85], [duration, 1]], "vocals": b_voice}
            if switch + .12 >= release:
                continue
            ramp_start = min(.32, .2 * release)
            for role in ("bass", "other"):
                a[role] = [[0, 1], [ramp_start, .82], [release-.12, .42],
                           [tone_switch, 0], [duration, 0]]
                b[role] = [[0, 0], [ramp_start, lead], [tone_switch, lead],
                           [pitch_takeover, 1]]
                if pitch_takeover < duration:
                    b[role].append([duration, 1])
            yield {"duration": duration, "a": a, "b": b, "bVoiceEntry": voice,
                   "name": f"intro-{lead:.2f}-drum-{switch:.3f}"}
