"""End-to-end smoke for the dj_set pipeline (no DB, no FastAPI).

Run:    py scripts/dj_set_smoke.py
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace


def _make_song(sid: str, *, title: str, bpm: float, energy: float,
               duration: float, camelot: str, genre: str, stems: bool,
               vocal_heavy: bool):
    """Build a LibrarySong-shaped namespace with phrase/cue/beats."""
    bar = 4 * 60.0 / bpm
    n_bars = max(8, int(duration / bar))
    beat_points = [round(i * 60.0 / bpm, 4) for i in range(int(duration * bpm / 60.0))]
    downbeats = [round(i * bar, 4) for i in range(n_bars + 1) if i * bar < duration]

    # Phrase map: intro / verse / chorus / verse / chorus / outro
    pm = []
    if vocal_heavy:
        labels = ["intro", "verse", "chorus", "verse", "chorus", "outro"]
    else:
        labels = ["intro", "build", "drop", "break", "drop", "outro"]
    seg = duration / len(labels)
    for i, lbl in enumerate(labels):
        pm.append({"start": round(i * seg, 3), "label": lbl})

    cps = [{"time": pm[1]["start"], "label": pm[1]["label"]},
           {"time": pm[-1]["start"], "label": "outro"}]

    return SimpleNamespace(
        id=sid, title=title, artist="t", duration=duration, bpm=bpm,
        energy=energy, camelot_key=camelot, key=None, genre=genre,
        phrase_map=pm, cue_points=cps, downbeats=downbeats,
        beat_points=beat_points,
        stems={"vocals": "v", "drums": "d", "bass": "b", "other": "o"} if stems else None,
        style=None,
    )


def main() -> int:
    sys.path.insert(0, ".")
    from app.modules.dj_set import service as dj_set_service

    songs = [
        _make_song("s1", title="Intro Track",  bpm=92,  energy=0.45,
                   duration=200, camelot="8A", genre="hip hop", stems=True, vocal_heavy=False),
        _make_song("s2", title="Groove Mid",   bpm=95,  energy=0.55,
                   duration=210, camelot="8A", genre="funk",    stems=True, vocal_heavy=True),
        _make_song("s3", title="Build Up",     bpm=98,  energy=0.65,
                   duration=205, camelot="9A", genre="hip hop", stems=True, vocal_heavy=False),
        _make_song("s4", title="Big Peak",     bpm=100, energy=0.85,
                   duration=215, camelot="9A", genre="trap",    stems=True, vocal_heavy=False),
        _make_song("s5", title="Reset Vibe",   bpm=92,  energy=0.40,
                   duration=190, camelot="8A", genre="rnb",     stems=True, vocal_heavy=True),
        _make_song("s6", title="Closer Calm",  bpm=88,  energy=0.35,
                   duration=180, camelot="7A", genre="ballad",  stems=True, vocal_heavy=True),
    ]

    print("== generate_dj_sets ==")
    result = dj_set_service.generate_dj_sets(songs, beam_width=12, drop_failed=False)

    print(f"  profiles: {len(result['profiles'])}")
    print(f"  edges:    {len(result['edges'])} (full pairwise)")
    print(f"  sets:     {len(result['sets'])}")

    for s in result["sets"]:
        print(f"\n  -- template={s['template']} score={s['score']} adj={s['adjusted_score']}")
        print(f"     tracks: {' -> '.join(s['tracks'])}")
        print(f"     arc:    {s['narrative_arc']}")
        print(f"     curve:  {s['energy_curve']}")
        print(f"     warnings: {s['warnings']}")
        print(f"     quality: passed={s['quality']['passed']} errors={s['quality']['errors']}")
        for p in s["plans"][:2]:
            spec = p.get("spec", {})
            print(f"       plan: {p['from']}->{p['to']} rule={p['rule']} purpose={p['purpose']}")
            print(f"             from={spec.get('from_at_sec')} to={spec.get('to_at_sec')} dur={spec.get('duration_sec')}s")
            print(f"             stems={'yes' if spec.get('stem_curves') else 'no'} reinforce={'yes' if spec.get('beat_reinforce') else 'no'}")

    print("\n== preview_transition s1->s4 ==")
    pv = dj_set_service.preview_transition(songs[0], songs[3])
    print(json.dumps({k: v for k, v in pv.items() if k != "edge"}, indent=2, ensure_ascii=False))
    print("edge:", json.dumps(pv["edge"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
