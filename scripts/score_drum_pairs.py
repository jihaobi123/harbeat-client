"""Generate auditable drum pair scores from song-level analysis JSONL.

Input rows use ``{"song_id": "...", "drum_analysis": {...}}``. By default
all unordered song pairs are scored. Use --pairs to limit work to selected
``song_a_id``/``song_b_id`` pairs. The flat output can be reviewed and then
augmented with ``human_band`` for threshold calibration.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any, Iterable

from preprocessing.engines.drum_pair_similarity import score_drum_pair


def load_songs(path: Path) -> dict[str, dict[str, Any]]:
    songs: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        song_id = str(row["song_id"])
        if song_id in songs:
            raise ValueError(f"{path}:{line_number}: duplicate song_id {song_id!r}")
        analysis = row.get("drum_analysis")
        if not isinstance(analysis, dict):
            raise ValueError(f"{path}:{line_number}: drum_analysis must be an object")
        songs[song_id] = analysis
    if len(songs) < 2:
        raise ValueError(f"{path}: at least two songs are required")
    return songs


def load_selected_pairs(path: Path) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        left = str(row["song_a_id"])
        right = str(row["song_b_id"])
        if left == right:
            raise ValueError(f"{path}:{line_number}: a song cannot pair with itself")
        pair = tuple(sorted((left, right)))
        if pair not in seen:
            seen.add(pair)
            result.append(pair)
    return result


def generate_pair_rows(
    songs: dict[str, dict[str, Any]],
    pairs: Iterable[tuple[str, str]] | None = None,
    *,
    cache_dir: Path | None = None,
) -> list[dict[str, Any]]:
    selected = list(pairs) if pairs is not None else list(
        itertools.combinations(sorted(songs), 2)
    )
    rows: list[dict[str, Any]] = []
    for left, right in selected:
        if left not in songs or right not in songs:
            missing = sorted({value for value in (left, right) if value not in songs})
            raise ValueError(f"pair references unknown song_id: {', '.join(missing)}")
        result = score_drum_pair(
            left,
            songs[left],
            right,
            songs[right],
            cache_dir=cache_dir,
        )
        scores = result["scores"]
        rows.append(
            {
                "song_a_id": result["pair"]["song_ids"][0],
                "song_b_id": result["pair"]["song_ids"][1],
                "score_version": result["version"],
                "score": scores["drum_overlap_score"],
                "category_overlap_score": scores["category_overlap_score"],
                "rhythm_landing_similarity_score": scores[
                    "rhythm_landing_similarity_score"
                ],
                "status": result["status"],
                "needs_review": result["needs_review"],
                "proposal_action": result["proposal_route"]["proposal_action"],
                "raw_threshold_route": result["raw_threshold_route"],
                "quality_flags": result["quality_flags"],
                "human_band": None,
                "cache_key": result["cache"]["key"],
                "cache_hit": result["cache"]["hit"],
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--songs", required=True, type=Path)
    parser.add_argument("--pairs", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    songs = load_songs(args.songs)
    pairs = load_selected_pairs(args.pairs) if args.pairs else None
    rows = generate_pair_rows(songs, pairs, cache_dir=args.cache_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps({"status": "ready", "pairs": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
