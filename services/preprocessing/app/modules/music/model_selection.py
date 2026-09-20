from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

QualityMode = Literal["balanced", "hq", "fast"]


@dataclass(frozen=True)
class ModelBundle:
    stem_separator: str
    beat_tracker: str
    key_detector: str
    time_stretch: str
    transition_mixer: str
    mastering: str
    style_engine: str


# 选择“成熟度高+落地广泛”的模型/工具组合
# - 分离: Demucs htdemucs_ft（工业实践成熟）
# - 节奏/调性: Essentia（若不可用可回退 librosa）
# - 变速: Rubber Band（高质量 time-stretch）
# 实际已集成的模型/工具组合
# - 分离: Demucs htdemucs（4-track: drums/bass/vocals/other）
# - 节奏: librosa beat_track
# - 变速: librosa time_stretch（pyrubberband 回退，Windows 无 rubberband CLI）
# - DSP: pedalboard（Compressor / EQ / Limiter）
# - 母带: pyloudnorm EBU R128
# - 风格增强: 规则链路（stem remix + transient boost + groove pump）
MODEL_PRESETS: dict[QualityMode, ModelBundle] = {
    "balanced": ModelBundle(
        stem_separator="demucs:htdemucs",
        beat_tracker="librosa:beat_track",
        key_detector="librosa:chroma_cqt",
        time_stretch="librosa:time_stretch",
        transition_mixer="numpy:crossfade",
        mastering="pyloudnorm:ebu_r128",
        style_engine="pedalboard:dsp_chain+stem_remix",
    ),
    "hq": ModelBundle(
        stem_separator="demucs:htdemucs",
        beat_tracker="librosa:beat_track",
        key_detector="librosa:chroma_cqt",
        time_stretch="pyrubberband:default",
        transition_mixer="numpy:crossfade",
        mastering="pyloudnorm:ebu_r128",
        style_engine="pedalboard:dsp_chain+stem_remix",
    ),
    "fast": ModelBundle(
        stem_separator="librosa:hpss",
        beat_tracker="librosa:beat_track",
        key_detector="librosa:chroma_cqt",
        time_stretch="librosa:time_stretch",
        transition_mixer="numpy:crossfade",
        mastering="pyloudnorm:ebu_r128",
        style_engine="pedalboard:dsp_chain+hpss_remix",
    ),
}


def pick_model_bundle(quality_mode: QualityMode) -> ModelBundle:
    return MODEL_PRESETS.get(quality_mode, MODEL_PRESETS["balanced"])


def pick_style_engine(style: str, quality_mode: QualityMode) -> str:
    normalized = style.strip().lower()
    bundle = pick_model_bundle(quality_mode)
    # 风格引擎可按风格切换；当前统一走成熟链路，后续可细分每个舞种模型
    if normalized in {"breaking", "breakin", "bboy", "popping", "locking", "hiphop", "waacking", "house", "krump"}:
        return bundle.style_engine
    return "rule_based:tempo_eq_transient"
