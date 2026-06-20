"""Decision tree for the HarBeat automatic DJ mixer package."""

from __future__ import annotations


class StrategySelector:
    """Select one of the package's five EQ-band mixing strategies."""

    STRATEGY_MAPPING = {
        1: "standard_blend",
        2: "energy_lift",
        3: "energy_drop",
        4: "tempo_compat",
        5: "cross_style",
    }

    STRATEGY_TO_NUM = {name: num for num, name in STRATEGY_MAPPING.items()}
    USER_ALIASES = {
        "1": "standard_blend",
        "standard": "standard_blend",
        "standard_blend": "standard_blend",
        "smooth": "standard_blend",
        "smooth_blend": "standard_blend",
        "2": "energy_lift",
        "energy_lift": "energy_lift",
        "energy_up": "energy_lift",
        "soft": "energy_lift",
        "soft_bass_swap": "energy_lift",
        "filter": "energy_lift",
        "filter_sweep": "energy_lift",
        "3": "energy_drop",
        "energy_drop": "energy_drop",
        "energy_down": "energy_drop",
        "vocal": "energy_drop",
        "vocal_safe": "energy_drop",
        "4": "tempo_compat",
        "tempo": "tempo_compat",
        "tempo_compat": "tempo_compat",
        "rhythm": "tempo_compat",
        "hard_bass_swap": "tempo_compat",
        "5": "cross_style",
        "cross_style": "cross_style",
        "style_cross": "cross_style",
        "overlap": "cross_style",
    }

    @staticmethod
    def select(
        features1: dict[str, float],
        features2: dict[str, float],
        *,
        user_strategy: str | None = None,
    ) -> tuple[int, str, str]:
        """Return ``(strategy_num, strategy_name, reason)``."""
        override = StrategySelector.resolve_user_strategy(user_strategy)
        if override:
            return (
                StrategySelector.STRATEGY_TO_NUM[override],
                override,
                f"user override: {override}",
            )

        bpm1 = float(features1.get("bpm") or 120.0)
        bpm2 = float(features2.get("bpm") or 120.0)
        energy1 = max(0.001, float(features1.get("energy") or 0.5))
        energy2 = max(0.001, float(features2.get("energy") or 0.5))
        bpm_diff = abs(bpm1 - bpm2)
        energy_ratio = energy2 / energy1
        freq_diff = (
            abs(float(features1.get("low_ratio", 0.35)) - float(features2.get("low_ratio", 0.35)))
            + abs(float(features1.get("mid_ratio", 0.40)) - float(features2.get("mid_ratio", 0.40)))
            + abs(float(features1.get("high_ratio", 0.25)) - float(features2.get("high_ratio", 0.25)))
        )

        if freq_diff > 0.8:
            strategy_num = 5
            reason = f"frequency difference high ({freq_diff:.2f})"
        elif energy_ratio > 1.5:
            strategy_num = 2
            reason = f"energy increase ({energy_ratio:.2f}x)"
        elif energy_ratio < 0.67:
            strategy_num = 3
            reason = f"energy decrease ({energy_ratio:.2f}x)"
        elif bpm_diff > 15:
            strategy_num = 4
            reason = f"BPM difference high ({bpm_diff:.0f})"
        else:
            strategy_num = 1
            reason = "similar energy"

        strategy_name = StrategySelector.STRATEGY_MAPPING[strategy_num]
        return strategy_num, strategy_name, reason

    @staticmethod
    def resolve_user_strategy(value: str | None) -> str | None:
        if not value or value == "auto":
            return None
        raw = value.strip().lower()
        return StrategySelector.USER_ALIASES.get(raw)
