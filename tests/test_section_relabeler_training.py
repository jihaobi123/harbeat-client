import numpy as np

from app.modules.library.section_relabeler import STRUCTURE_LABELS, feature_names
from scripts.train_section_relabeler import cross_validate


def test_grouped_training_selects_a_safe_positive_gain_model() -> None:
    rows = []
    targets = []
    originals = []
    groups = []
    probability_offset = 0
    for track_index in range(20):
        for label_index, label in enumerate(STRUCTURE_LABELS):
            vector = np.zeros(len(feature_names()), dtype=np.float64)
            vector[probability_offset + label_index] = 1.0
            vector[8 + label_index] = 0.0
            rows.append(vector)
            targets.append(label)
            originals.append(
                STRUCTURE_LABELS[(label_index + 1) % len(STRUCTURE_LABELS)]
                if track_index % 2 == 0
                else label
            )
            groups.append(f"track-{track_index}")

    _, threshold, _, report = cross_validate(
        np.vstack(rows),
        np.asarray(targets),
        np.asarray(originals),
        np.asarray(groups),
        folds=5,
        minimum_precision=0.8,
    )

    assert threshold <= 1.0
    assert report["folds"] == 5
    assert report["gated_metrics"]["net_gain"] > 0
    assert report["gated_metrics"]["override_precision"] >= 0.8
