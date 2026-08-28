from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.prepare_public_music_benchmark import render_clips, select_candidates


def test_selector_preserves_multilabels_and_diversifies_artists(tmp_path: Path) -> None:
    genre = tmp_path / "genre.tsv"
    genre.write_text(
        "TRACK_ID\tARTIST_ID\tALBUM_ID\tPATH\tDURATION\tTAGS\n"
        "track_0000001\ta1\tal1\t1/1.mp3\t120\tgenre---funk\tgenre---disco\n"
        "track_0000002\ta1\tal1\t2/2.mp3\t121\tgenre---funk\n"
        "track_0000003\ta2\tal2\t3/3.mp3\t122\tgenre---funk\n"
        "track_0000004\ta3\tal3\t4/4.mp3\t123\tgenre---disco\n"
        "track_0000005\ta4\tal4\t5/5.mp3\t124\tgenre---house\n",
        encoding="utf-8",
    )
    metadata = tmp_path / "meta.tsv"
    metadata.write_text(
        "TRACK_ID\tARTIST_ID\tALBUM_ID\tTRACK_NAME\tARTIST_NAME\tALBUM_NAME\tRELEASEDATE\tURL\n"
        + "\n".join(
            f"track_{index:07d}\ta{index}\tal{index}\tTrack {index}\tArtist {index}\tAlbum\t2020\thttp://x/{index}"
            for index in range(1, 6)
        )
        + "\n",
        encoding="utf-8",
    )

    result = select_candidates(genre, metadata, per_style=2)

    first = next(item for item in result if item["source_track_id"] == "track_0000001")
    assert first["expected_styles"] == ["disco", "funk"]
    funk_artists = {item["artist_group"] for item in result if "funk" in item["expected_styles"]}
    assert len(funk_artists) >= 2
    assert any("house" in item["expected_styles"] for item in result)


def test_clip_renderer_reads_only_requested_window(tmp_path: Path) -> None:
    sr = 8000
    source = tmp_path / "source.wav"
    sf.write(source, np.arange(sr * 10, dtype=np.float32) / (sr * 10), sr)
    rows = [{"clip_id": "clip-1", "local_audio": str(source)}]

    result = render_clips(rows, tmp_path / "clips", start_seconds=2.0, duration_seconds=3.0)
    clip, clip_sr = sf.read(rows[0]["local_clip"])

    assert result == {"ready": 1, "failed": 0, "total": 1}
    assert clip_sr == sr
    assert len(clip) == sr * 3
    assert rows[0]["start_seconds"] == 2.0
    assert rows[0]["end_seconds"] == 5.0
