import numpy as np
import pytest

from scripts.evaluate_section_relabeler_candidates import predict
from scripts.train_section_relabeler_candidates import align_cache, candidate_matrices


def test_candidate_feature_dimensions_are_frozen():
    base = np.zeros((2, 1100), dtype=float)
    audio = np.zeros((2, 312), dtype=float)
    stems = np.zeros((2, 208), dtype=float)

    candidates = {candidate_id: matrix for candidate_id, _, _, _, matrix in candidate_matrices(base, audio, stems)}

    assert candidates["c01_songformer_local_v1"].shape == (2, 52)
    assert candidates["c02_whole_song_structure_v2"].shape == (2, 76)
    assert candidates["c03_encoder_projection_v3"].shape == (2, 1100)
    assert candidates["c04_mixed_audio_v4"].shape == (2, 1412)
    assert candidates["c05_demucs_stems_v5"].shape == (2, 1308)
    assert candidates["c06_audio_and_stems_v6"].shape == (2, 1620)


def test_cache_alignment_uses_track_and_segment_identity():
    records = [
        {"track_id": "song-b", "segment_index": 1},
        {"track_id": "song-a", "segment_index": 0},
    ]
    lookup = {
        ("song-a", 0): np.asarray([1.0, 2.0]),
        ("song-b", 1): np.asarray([3.0, 4.0]),
    }

    result = align_cache(records, lookup, 2, "test")

    assert result.tolist() == [[3.0, 4.0], [1.0, 2.0]]


def test_cache_alignment_fails_closed_when_a_segment_is_missing():
    records = [{"track_id": "song-a", "segment_index": 0}]

    with pytest.raises(ValueError, match="missing 1 trainable segment"):
        align_cache(records, {}, 2, "test")


def test_json_linear_model_prediction_uses_residual_gate():
    model = {
        "candidate_id": "synthetic",
        "parameters": {
            "feature_mean": [0.0, 0.0],
            "feature_scale": [1.0, 1.0],
            "coefficients": [[2.0, 0.0], [0.0, 2.0]],
            "intercept": [0.0, 0.0],
            "labels": ["chorus", "verse"],
            "override_threshold": 0.8,
        },
    }
    features = np.asarray([[2.0, 0.0], [0.0, 0.1]])
    originals = np.asarray(["verse", "chorus"])

    final, proposed, confidence = predict(model, features, originals)

    assert proposed.tolist() == ["chorus", "verse"]
    assert final.tolist() == ["chorus", "chorus"]
    assert confidence[0] > 0.8
    assert confidence[1] < 0.8
