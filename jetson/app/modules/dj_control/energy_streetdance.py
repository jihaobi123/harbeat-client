"""Street-dance energy v2 — fingerprint-driven, style-aware.

Inputs : LibrarySong.music_features['dj']  (the 25-dim fingerprint, already
         backfilled by dj_feature_extractor.py).
Output : StreetEnergy with continuous total, 5-bucket label, 7 perceptual
         factors and a Chinese explain string.

Three layers:
  L1 physical    — 25 fingerprint dims (no audio decode needed)
  L2 perceptual  — 7 factors derived from L1 (style-agnostic, 0..1)
  L3 final       — weighted sum where weights depend on dance style; same
                   song scores differently when ranking for breaking vs house

Design notes (intentional):
  * No ML / embeddings. Hand-tuned weights are explainable & adjustable.
  * No new audio features extracted at runtime — < 1ms per song.
  * 5 perceptual buckets for UI ("高能"), continuous total for sequencer.
  * v1 compute_dance_energy() is kept as fallback when style=None or features
    are missing — see energy_hiphop.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Layer 2 — 7 perceptual factors (each 0..1, style-agnostic)
# --------------------------------------------------------------------------- #
def _sigmoid(x: float, k: float = 6.0) -> float:
    return 1.0 / (1.0 + math.exp(-k * x))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _safe(d: dict, key: str, default: float = 0.0) -> float:
    v = d.get(key, default)
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def perceptual_factors(dj: dict) -> dict[str, float]:
    """Compute 7 perceptual factors from a fingerprint dict (music_features['dj'])."""
    bass_dom = _safe(dj, "bass_dominance")
    sub_bass = _safe(dj, "sub_bass_score")
    drums_rms = _safe(dj, "drums_rms")
    d2v = _safe(dj, "drums_to_vocals_ratio")
    groove = _safe(dj, "groove_complexity")
    bpm = _safe(dj, "bpm")
    centroid = _safe(dj, "spectral_centroid")
    zcr = _safe(dj, "zero_crossing_rate")
    beat_density = _safe(dj, "beat_density")
    contrast = _safe(dj, "spectral_contrast_mean")
    vocals_rms = _safe(dj, "vocals_rms")
    energy_flat = _safe(dj, "energy", default=0.5)

    bass_punch = _sigmoid((bass_dom * 1.4 + sub_bass) / 2.0 - 0.4)
    drum_drive = math.tanh(drums_rms * 1.6) * min(d2v / 3.0, 1.0) if d2v > 0 else math.tanh(drums_rms * 1.6) * 0.4
    groove_intensity = _clamp(groove * 4.5)
    tempo_drive = _clamp((bpm - 75.0) / 65.0)
    attack_brightness = _clamp(centroid / 4200.0) * 0.6 + _clamp(zcr * 4.0) * 0.4
    density_pulse = _clamp(beat_density / 2.4)
    dynamic_thrust = _clamp(contrast / 28.0)
    # Auxiliary (not part of weighted sum, used for explain only)
    vocal_intensity = _clamp(vocals_rms * energy_flat * 1.3)

    return {
        "bass_punch": round(bass_punch, 4),
        "drum_drive": round(drum_drive, 4),
        "groove_intensity": round(groove_intensity, 4),
        "tempo_drive": round(tempo_drive, 4),
        "attack_brightness": round(attack_brightness, 4),
        "density_pulse": round(density_pulse, 4),
        "dynamic_thrust": round(dynamic_thrust, 4),
        "vocal_intensity": round(vocal_intensity, 4),
    }


# --------------------------------------------------------------------------- #
# Layer 3 — style-specific weights + offsets
# --------------------------------------------------------------------------- #
# Weights per (style, factor). Each row sums to 1.00 (sanity-checked at import).
STREET_ENERGY_PROFILES: dict[str, dict[str, float]] = {
    "breaking": {
        "bass_punch": 0.18, "drum_drive": 0.22, "groove_intensity": 0.22,
        "tempo_drive": 0.10, "attack_brightness": 0.10, "density_pulse": 0.10,
        "dynamic_thrust": 0.08,
    },
    "hiphop": {
        "bass_punch": 0.28, "drum_drive": 0.22, "groove_intensity": 0.10,
        "tempo_drive": 0.08, "attack_brightness": 0.05, "density_pulse": 0.10,
        "dynamic_thrust": 0.17,
    },
    "popping": {
        "bass_punch": 0.20, "drum_drive": 0.18, "groove_intensity": 0.22,
        "tempo_drive": 0.10, "attack_brightness": 0.12, "density_pulse": 0.08,
        "dynamic_thrust": 0.10,
    },
    "locking": {
        "bass_punch": 0.15, "drum_drive": 0.18, "groove_intensity": 0.10,
        "tempo_drive": 0.12, "attack_brightness": 0.20, "density_pulse": 0.10,
        "dynamic_thrust": 0.15,
    },
    "house": {
        "bass_punch": 0.15, "drum_drive": 0.25, "groove_intensity": 0.05,
        "tempo_drive": 0.20, "attack_brightness": 0.15, "density_pulse": 0.15,
        "dynamic_thrust": 0.05,
    },
    "krump": {
        "bass_punch": 0.30, "drum_drive": 0.20, "groove_intensity": 0.05,
        "tempo_drive": 0.05, "attack_brightness": 0.05, "density_pulse": 0.05,
        "dynamic_thrust": 0.30,
    },
    "waacking": {
        "bass_punch": 0.10, "drum_drive": 0.20, "groove_intensity": 0.05,
        "tempo_drive": 0.18, "attack_brightness": 0.20, "density_pulse": 0.12,
        "dynamic_thrust": 0.15,
    },
    "generic": {
        "bass_punch": 0.20, "drum_drive": 0.20, "groove_intensity": 0.10,
        "tempo_drive": 0.12, "attack_brightness": 0.12, "density_pulse": 0.10,
        "dynamic_thrust": 0.16,
    },
}

# Per-style baseline offset added before clamp. Encodes "this genre just
# *feels* louder/heavier than the average pop track of equal RMS".
STYLE_OFFSETS: dict[str, float] = {
    "breaking": 0.05,
    "hiphop":   0.02,
    "popping":  0.00,
    "locking":  0.00,
    "house":    0.00,
    "krump":    0.08,
    "waacking": -0.03,
    "generic":  0.00,
}

# Sanity: weights per style sum to 1.0 ± 0.01
for _style, _w in STREET_ENERGY_PROFILES.items():
    _s = sum(_w.values())
    assert abs(_s - 1.0) < 0.01, f"style {_style} weights sum to {_s}, must be 1.0"
del _style, _w, _s

# --------------------------------------------------------------------------- #
# Bucket discretization (5 levels)
# --------------------------------------------------------------------------- #
BUCKETS: list[tuple[str, str, float, float]] = [
    # (key, label_zh, lo, hi)  hi is exclusive except top
    ("cold", "冷场", 0.00, 0.25),
    ("warm", "暖场", 0.25, 0.45),
    ("mid",  "中段", 0.45, 0.65),
    ("high", "高能", 0.65, 0.80),
    ("peak", "炸场", 0.80, 1.01),  # 1.01 to include 1.0
]

BUCKET_COLORS = {
    "cold": "#6B7280",
    "warm": "#3B82F6",
    "mid":  "#10B981",
    "high": "#F59E0B",
    "peak": "#EF4444",
}


def bucket_for(total: float) -> tuple[str, str]:
    for key, label, lo, hi in BUCKETS:
        if lo <= total < hi:
            return key, label
    return "cold", "冷场"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
@dataclass
class StreetEnergy:
    total: float                       # 0..1, used by sequencer
    bucket: str                        # 'cold'|'warm'|'mid'|'high'|'peak'
    bucket_label_zh: str
    bucket_color: str
    style_used: str                    # which weight profile was applied
    factors: dict[str, float] = field(default_factory=dict)
    bpm: float = 0.0
    camelot_key: str | None = None
    duration: float = 0.0
    explain_zh: str = ""

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "bucket": self.bucket,
            "bucket_label_zh": self.bucket_label_zh,
            "bucket_color": self.bucket_color,
            "style_used": self.style_used,
            "factors": self.factors,
            "bpm": self.bpm,
            "camelot_key": self.camelot_key,
            "duration": self.duration,
            "explain_zh": self.explain_zh,
        }


def _build_explain(bucket_label: str, factors: dict[str, float], bpm: float, style: str) -> str:
    """Pick the top-2 contributing factors and surface them in Chinese."""
    naming = {
        "bass_punch": "低频冲击",
        "drum_drive": "鼓主导",
        "groove_intensity": "切分密集",
        "tempo_drive": "节奏快",
        "attack_brightness": "高频亮",
        "density_pulse": "节拍密",
        "dynamic_thrust": "Drop 反差大",
        "vocal_intensity": "人声紧",
    }
    profile = STREET_ENERGY_PROFILES.get(style, STREET_ENERGY_PROFILES["generic"])
    weighted = sorted(
        ((k, factors.get(k, 0.0) * profile.get(k, 0.0)) for k in profile),
        key=lambda kv: kv[1],
        reverse=True,
    )
    tops = [naming[k] for k, _ in weighted[:2]]
    bpm_str = f"BPM={int(round(bpm))}" if bpm > 0 else ""
    bits = [bucket_label] + tops + ([bpm_str] if bpm_str else [])
    return " · ".join(bits)


def compute_street_energy(song, style: str | None = "generic") -> StreetEnergy:
    """Compute the v2 street-dance energy for a LibrarySong-like object.

    `song.music_features['dj']` must be the fingerprint dict produced by
    `dj_feature_extractor.extract_dj_features()`. If missing, returns a
    StreetEnergy with total=0 / bucket='cold' / style_used='no_dj' so the
    caller can decide to fall back to the v1 scorer (energy_hiphop).
    """
    style = (style or "generic").lower()
    if style not in STREET_ENERGY_PROFILES:
        style = "generic"

    mf = getattr(song, "music_features", None) or {}
    dj = mf.get("dj") if isinstance(mf, dict) else None
    if not (dj and isinstance(dj, dict)):
        return StreetEnergy(
            total=0.0,
            bucket="cold",
            bucket_label_zh="冷场",
            bucket_color=BUCKET_COLORS["cold"],
            style_used="no_dj",
            factors={},
            bpm=float(getattr(song, "bpm", 0) or 0),
            camelot_key=getattr(song, "camelot_key", None),
            duration=float(getattr(song, "duration", 0) or 0),
            explain_zh="无指纹数据",
        )

    factors = perceptual_factors(dj)
    profile = STREET_ENERGY_PROFILES[style]
    raw = sum(factors[k] * w for k, w in profile.items())
    total = _clamp(raw + STYLE_OFFSETS.get(style, 0.0))
    bkt, label = bucket_for(total)
    bpm = _safe(dj, "bpm", default=float(getattr(song, "bpm", 0) or 0))

    return StreetEnergy(
        total=round(total, 4),
        bucket=bkt,
        bucket_label_zh=label,
        bucket_color=BUCKET_COLORS[bkt],
        style_used=style,
        factors=factors,
        bpm=round(bpm, 1),
        camelot_key=getattr(song, "camelot_key", None),
        duration=float(getattr(song, "duration", 0) or 0),
        explain_zh=_build_explain(label, factors, bpm, style),
    )


def list_buckets() -> list[dict]:
    """For UI: give the 5-bucket schema (key, label_zh, color, range)."""
    return [
        {
            "key": k, "label_zh": l, "color": BUCKET_COLORS[k],
            "lo": lo, "hi": (hi if hi <= 1.0 else 1.0),
        }
        for k, l, lo, hi in BUCKETS
    ]


def list_style_profiles() -> list[dict]:
    """For UI/debug: dump the weight tables."""
    return [
        {
            "style": s,
            "weights": dict(w),
            "offset": STYLE_OFFSETS.get(s, 0.0),
        }
        for s, w in STREET_ENERGY_PROFILES.items()
    ]
