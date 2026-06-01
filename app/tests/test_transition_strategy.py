from app.modules.dj_control.transition_strategy import (
    TransitionContext,
    list_cross_style_strategies,
    select_cross_style_strategy,
)


def ctx(**overrides):
    base = dict(
        bpmDiff=0.0,
        bpmDiffRatio=0.02,
        tempoRelation="close",
        keyDistance=0,
        genreDistance=0.2,
        energyDiff=0.1,
        vocalConflictRisk=0.1,
        phraseBarsAvailable=8,
        stemsAvailable=True,
    )
    base.update(overrides)
    return TransitionContext(**base)


def test_lists_eight_cross_style_strategies():
    keys = {item["key"] for item in list_cross_style_strategies()}
    assert keys == {
        "echo_out_hard_drop",
        "percussion_bridge",
        "stem_strip_rebuild",
        "auto_bpm_ramp",
        "half_time_double_time_pivot",
        "neutral_fx_bridge",
        "breakdown_reset",
        "impact_slam_cut",
    }


def test_selector_covers_each_cross_style_strategy():
    cases = [
        (ctx(bpmDiffRatio=0.20, keyDistance=6, genreDistance=0.9, stemsAvailable=True), "echo_out_hard_drop"),
        (ctx(genreDistance=0.7, stemsAvailable=True), "percussion_bridge"),
        (ctx(vocalConflictRisk=0.6, stemsAvailable=True), "stem_strip_rebuild"),
        (ctx(bpmDiffRatio=0.10, tempoRelation="unrelated"), "auto_bpm_ramp"),
        (ctx(bpmDiffRatio=0.48, tempoRelation="double-time"), "half_time_double_time_pivot"),
        (ctx(bpmDiffRatio=0.20, keyDistance=6, genreDistance=0.9, stemsAvailable=False), "neutral_fx_bridge"),
        (ctx(energyDiff=0.42, genreDistance=0.2), "breakdown_reset"),
        (ctx(bpmDiffRatio=0.13, tempoRelation="unrelated", genreDistance=0.3), "impact_slam_cut"),
    ]
    for context, expected in cases:
        strategy = select_cross_style_strategy(context)
        assert strategy is not None
        assert strategy.key == expected


def test_selector_keeps_compatible_pairs_on_standard_blend():
    assert select_cross_style_strategy(ctx()) is None
