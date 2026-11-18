"""Plan from two Jetson analysis job results and source-matched LRC evidence."""

import argparse
import hashlib
import json
from pathlib import Path

from .transition_policy import propose_pair
from .transition_cues import read_cues


def load_track(path):
    record = json.loads(path.read_text())
    job = record["job"]
    track = job["track"]
    source = Path(job["source"])
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    if digest.hexdigest() != track["provenance"]["masterSha256"]:
        raise ValueError("audio does not match the analysis report")
    return track


def supplement_intro(track, evidence):
    provenance = track["provenance"]
    if (evidence.get("schema") != "harbeat.intro-beat-evidence.v1"
            or evidence.get("producer") != "jetson"
            or evidence.get("trackId") != track["id"]
            or any(evidence.get(key) != provenance[key]
                   for key in ("masterSha256", "reportSha256", "runId"))
            or evidence.get("drumSupported", 0) / max(evidence.get("beatCount", 0), 1) < .8):
        raise ValueError("intro beat evidence does not match this analysis run")
    existing = track["alignment"]["bars"]
    prefix = evidence["bars"]
    if not prefix or not existing or prefix[-1]["end"] > existing[0]["start"] + .001:
        raise ValueError("intro evidence would overwrite existing measurements")
    return {**track, "alignment": {**track["alignment"], "bars": prefix + existing}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a_result", type=Path)
    parser.add_argument("b_result", type=Path)
    parser.add_argument("lyrics", type=Path, nargs="?",
                        help='JSON with masterSha256 and the same recording\'s LRC in lrc')
    parser.add_argument("--b-entry", type=float, help="existing B cue in source seconds")
    parser.add_argument("--a-reference", type=float, help="existing A cue in source seconds")
    parser.add_argument("--b-intro-evidence", type=Path, help="source-bound missing intro beat observations")
    args = parser.parse_args()
    a, b = load_track(args.a_result), load_track(args.b_result)
    intro_evidence = args.b_intro_evidence or (args.b_result.parent / 'transition-intro-beats.json')
    if args.b_intro_evidence or intro_evidence.is_file():
        try:
            b = supplement_intro(b, json.loads(intro_evidence.read_text()))
        except (OSError, ValueError, KeyError, TypeError):
            if args.b_intro_evidence:
                raise
    evidence = json.loads(args.lyrics.read_text()) if args.lyrics else None
    print(json.dumps(propose_pair(a, b, evidence, a_reference=args.a_reference, b_entry=args.b_entry,
                                  a_cues=read_cues(args.a_result.parent, a),
                                  b_cues=read_cues(args.b_result.parent, b)),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
