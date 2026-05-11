"""Test the audio analysis pipeline and verify online mix data production.

Usage:
    PYTHONPATH=. python test_analysis_pipeline.py
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import soundfile as sf

def create_test_audio(path: str, bpm: float = 128.0, duration_sec: float = 30.0):
    """Create a synthetic test audio file with a clear kick+snare beat pattern."""
    sr = 44100
    beat_interval = 60.0 / bpm
    total_samples = int(sr * duration_sec)
    audio = np.zeros((total_samples, 2), dtype=np.float32)

    # Kick on beats 1 and 3, snare on 2 and 4
    kick = np.sin(2 * np.pi * 55 * np.linspace(0, 0.06, int(sr * 0.06))) * np.exp(-np.linspace(0, 8, int(sr * 0.06)))
    snare = (np.random.randn(int(sr * 0.08)) * np.exp(-np.linspace(0, 12, int(sr * 0.08)))).astype(np.float32) * 0.5

    for beat in range(int(duration_sec * bpm / 60)):
        t = beat * beat_interval
        sample = int(t * sr)
        beat_in_bar = beat % 4
        if beat_in_bar in (0, 2):  # Kick
            end = min(sample + len(kick), total_samples)
            audio[sample:end, 0] += kick[:end-sample]
            audio[sample:end, 1] += kick[:end-sample] * 0.8
        elif beat_in_bar in (1, 3):  # Snare
            end = min(sample + len(snare), total_samples)
            audio[sample:end, 0] += snare[:end-sample]
            audio[sample:end, 1] += snare[:end-sample] * 0.9

    # Hi-hat rhythm on 8th notes
    hh = np.sin(2 * np.pi * 8000 * np.linspace(0, 0.03, int(sr * 0.03))) * np.exp(-np.linspace(0, 15, int(sr * 0.03))) * 0.15
    for eighth in range(int(duration_sec * bpm * 2 / 60)):
        t = eighth * beat_interval / 2
        sample = int(t * sr)
        end = min(sample + len(hh), total_samples)
        audio[sample:end, 0] += hh[:end-sample]
        audio[sample:end, 1] += hh[:end-sample] * 0.7

    audio = audio / (np.max(np.abs(audio)) + 1e-8) * 0.9
    sf.write(path, audio, sr)
    print(f"  Created test audio: {path} ({duration_sec}s, {bpm} BPM, {sr} Hz)")
    return path

def test_analysis():
    """Test the full analysis pipeline."""
    print("=" * 60)
    print("TEST 1: Audio Analysis Pipeline")
    print("=" * 60)

    # Create test audio files with different BPMs
    data_dir = os.path.join(os.path.dirname(__file__), "data", "test_songs")
    os.makedirs(data_dir, exist_ok=True)

    test_tracks = [
        ("test_hiphop_128bpm.wav", 128.0, "Test HipHop Beat", "AI Producer"),
        ("test_house_100bpm.wav", 100.0, "Test House Beat", "AI Producer"),
    ]

    results = []
    for filename, bpm, title, artist in test_tracks:
        path = os.path.join(data_dir, filename)
        if not os.path.exists(path):
            create_test_audio(path, bpm=bpm, duration_sec=30.0)

        print(f"\n--- Analyzing: {title} ({bpm} BPM) ---")
        from app.modules.library.analysis import analyze_audio_file

        t0 = time.time()
        result = analyze_audio_file(path, title=title, artist=artist)
        elapsed = time.time() - t0

        print(f"  Analysis completed in {elapsed:.1f}s")
        print(f"  BPM:       {result.get('bpm')}")
        print(f"  Key:       {result.get('key')}  Camelot: {result.get('camelot_key')}")
        print(f"  Energy:    {result.get('energy')}")
        print(f"  Beats:     {len(result.get('beat_points', []))} points")
        print(f"  Downbeats: {len(result.get('downbeats', []))} points")
        print(f"  Structure: {len(result.get('cue_points', []))} cue points")
        print(f"  Phrases:   {len(result.get('phrase_map', []))} segments")
        print(f"  Beat conf: {result.get('beat_confidence')}")
        print(f"  Needs review: {result.get('beat_needs_review', False)}")

        # Show phrase map (what the DJ mixer uses for transitions)
        phrases = result.get('phrase_map', [])
        if phrases:
            print(f"\n  Phrase Map (for DJ transitions):")
            for p in phrases[:8]:
                print(f"    [{p.get('start',0):.1f}s - {p.get('end',0):.1f}s] {p.get('label','?')}")

        results.append(result)

    return results


def test_mix_plan():
    """Test DJ mix plan generation with analyzed data."""
    print("\n" + "=" * 60)
    print("TEST 2: DJ Mix Plan Generation (via API simulation)")
    print("=" * 60)

    from app.shared.database import SessionLocal
    from app.modules.users.models import User

    import app.modules.models  # noqa: F401 — register ORM mappers (LibrarySong → Song)

    db = SessionLocal()
    try:
        # Find existing user
        user = db.query(User).first()
        if not user:
            print("  No user found - please register first via API")
            return

        print(f"  Using user: {user.username} (id={user.id})")

        # Check library songs
        from app.modules.library.models import LibrarySong
        songs = db.query(LibrarySong).filter(
            LibrarySong.user_id == user.id,
            LibrarySong.bpm.isnot(None),
            LibrarySong.source_path.isnot(None),
            LibrarySong.source_path != "",
        ).all()

        if not songs:
            print("  No analyzed library songs with audio files found.")
            print("  Upload a song via API first: POST /api/library/upload")
            return

        print(f"  Found {len(songs)} analyzed songs in library:")
        for s in songs[:5]:
            print(f"    [{s.id}] {s.title} - {s.artist} | BPM={s.bpm} Key={s.camelot_key} Energy={s.energy}")

        # Try generating a mix plan via the service
        print("\n  Attempting DJ mix plan generation...")
        from app.modules.playlists.service import generate_dj_mix_plan
        from app.modules.playlists.schemas import DjMixPlanRequest

        plan_result = generate_dj_mix_plan(
            db,
            DjMixPlanRequest(
                style="hiphop",
                duration_minutes=3,
                user_id=user.id,
                quality_mode="fast",
                diversity=0.3,
                use_context_planner=False,
            ),
        )
        print(f"  Plan generated: {len(plan_result.playlist)} tracks, {len(plan_result.transition_plan)} transitions")
        for i, tr in enumerate(plan_result.transition_plan[:5]):
            print(f"    Transition {i+1}: #{tr.from_song_id}→#{tr.to_song_id} | "
                  f"technique={tr.transition_technique} | crossfade={tr.crossfade_sec:.1f}s | score={tr.score:.3f}")

    finally:
        db.close()


def test_upload_and_analyze():
    """Upload a test file through the analysis pipeline."""
    print("\n" + "=" * 60)
    print("TEST 3: Upload + Analysis + GrooveEngine Metadata")
    print("=" * 60)

    data_dir = os.path.join(os.path.dirname(__file__), "data", "test_songs")
    test_file = os.path.join(data_dir, "test_hiphop_128bpm.wav")
    if not os.path.exists(test_file):
        create_test_audio(test_file, bpm=128.0, duration_sec=30.0)

    # Run analysis
    from app.modules.library.analysis import analyze_audio_file
    result = analyze_audio_file(test_file, title="Test HipHop Beat", artist="AI Producer")

    # Build GrooveEngine TrackMetadata (simulating what groove_adapter does)
    print("\n  Building GrooveEngine TrackMetadata...")
    from app.modules.playlists.groove_adapter import library_song_to_track_metadata

    # Simulate a library song dict
    class FakeLib:
        def __init__(self):
            self.bpm = result.get('bpm')
            self.key = result.get('key')
            self.camelot_key = result.get('camelot_key')
            self.energy = result.get('energy')
            self.beat_points = result.get('beat_points', [])
            self.downbeats = result.get('downbeats', [])
            self.phrase_map = result.get('phrase_map', [])
            self.beat_confidence = result.get('beat_confidence')

    lib = FakeLib()
    meta = library_song_to_track_metadata(
        song_id=1, title="Test HipHop Beat", artist="AI Producer",
        duration=30.0, bpm=lib.bpm, key=lib.key, camelot_key=lib.camelot_key,
        energy=lib.energy, beat_points=lib.beat_points, downbeats=lib.downbeats,
        phrase_map=lib.phrase_map, beat_confidence=lib.beat_confidence,
        audio_path=test_file,
    )

    print(f"  TrackMetadata built successfully:")
    print(f"    track_id:       {meta.track_id}")
    print(f"    bpm:            {meta.beatgrid.bpm}")
    print(f"    bars:           {meta.bar_count()}")
    print(f"    phrases:        {len(meta.phrases)}")
    for p in meta.phrases[:5]:
        print(f"      [{p.start_bar}-{p.end_bar}] {p.phrase_type.value}")
    print(f"    key:            {meta.key.tonic} {meta.key.mode} (Camelot: {meta.key.camelot})")
    print(f"    beats:          {len(meta.beatgrid.beats)} total")
    print(f"    phrase anchors: {len(meta.phrase_anchors)}")
    print(f"    beat_analysis.phrase_sync_usable: {meta.beat_analysis.phrase_sync_usable}")
    print(f"    beat_analysis.long_blend_usable:  {meta.beat_analysis.long_blend_usable}")

    # Try transition planning between two copies of the same track (simulate a mix)
    print("\n  Running GrooveEngine TransitionPlanner...")
    from logic.brain import TransitionPlanner
    planner = TransitionPlanner()
    top = planner.top_candidates(meta, meta, limit=3)

    print(f"  Top {len(top)} transition candidates:")
    for i, c in enumerate(top):
        print(f"    #{i+1}: exit={c.track_a_exit_bar}→entry={c.track_b_entry_bar} | "
              f"overlap={c.overlap_beats} beats | strategy={c.strategy.value} | "
              f"score={c.total_score:.3f}")

    return result


if __name__ == "__main__":
    test_analysis()
    test_upload_and_analyze()
    test_mix_plan()
