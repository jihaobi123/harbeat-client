from types import SimpleNamespace

import numpy as np

from experiments.run_edmformer_isolated import (
    capture_raw_logits,
    six_class_frames,
)


def test_capture_raw_logits_preserves_the_upstream_prediction():
    sentinel = {"function_logits": "captured"}

    class PostprocessModule:
        @staticmethod
        def postprocess_functional_structure(logits, _config):
            assert logits is sentinel
            return [(0.0, "intro"), (2.0, "end")]

    class Pipeline:
        def predict_file(self, _audio):
            result = PostprocessModule.postprocess_functional_structure(
                sentinel, SimpleNamespace()
            )
            return [{"label": result[0][1], "start": 0.0, "end": 2.0}]

    prediction, captured = capture_raw_logits(
        Pipeline(), "song.wav", PostprocessModule
    )
    assert prediction[0]["label"] == "intro"
    assert captured is sentinel
    assert PostprocessModule.postprocess_functional_structure(
        sentinel, SimpleNamespace()
    )[0][1] == "intro"


def test_six_class_frames_softmaxes_only_the_edm_labels():
    logits = np.zeros((1, 2, 128), dtype=np.float32)
    label_to_id = {
        "intro": 0,
        "outro": 5,
        "silence": 6,
        "breakdown": 36,
        "buildup": 69,
        "drop": 70,
    }
    logits[0, 0, label_to_id["drop"]] = 4.0
    logits[0, 1, label_to_id["breakdown"]] = 3.0
    logits[0, :, 10] = 100.0

    frames = six_class_frames(
        logits,
        label_to_id=label_to_id,
        frame_rate=2.0,
        duration_sec=0.9,
    )
    assert len(frames) == 2
    assert frames[-1]["end_sec"] == 0.9
    assert frames[0]["probabilities"]["drop"] > 0.9
    assert frames[1]["probabilities"]["breakdown"] > 0.79
    assert abs(sum(frames[0]["probabilities"].values()) - 1.0) < 1e-6
