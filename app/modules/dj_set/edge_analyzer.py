"""Transition Edge Analyzer.

For every (A, B) pair of TrackProfiles, compute a multi-dimensional
transition score. This is the **constraint layer** the optimizer reads:
which pairs can be neighbors at all, which rule should be used, and
what the cost of using them is.

四个维度（每个维度独立打分，再加权得到 transition_score）:
  technical_score     — BPM lane / Camelot / beat_confidence / stems
  musical_score       — exit-vs-entry window energy / vocal conflict / low-end clash
  performance_score   — groove tightness / safe entry+exit availability
  risk_score          — 1.0 - max(任何会"翻车"的硬冲突)

Final:
  transition_score = 0.30 technical + 0.30 musical + 0.20 performance + 0.20 risk

Risk level:
  A   score >= 0.85    放心相邻
  B   0.75 ~ 0.85      可以相邻，注意 rule 选择
  C   0.60 ~ 0.75      只在能量曲线必要时使用
  D   < 0.60           默认禁止相邻
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.dj_set.section_energy import SectionEnergy
from app.modules.dj_set.track_profiler import TrackProfile


ALL_RULES = (
    # 11 ANALYZED rules (mixer_rules.ANALYZED_TRANSITIONS)
    "harmonic_blend",
    "eq_swap_4bar",
    "filter_sweep_high",
    "drop_swap",
    "echo_tail",
    "loop_roll",
    "spin_back",
    "drum_only_bridge",
    "key_lift",
    "reverb_throw",
    "back_to_back_drop",
    # 7 RAW rules (mixer_rules.RAW_TRANSITIONS) — fallback when stems/beats missing
    "raw_xfade_3s",
    "raw_xfade_6s",
    "raw_xfade_10s",
    "raw_hard_cut",
    "raw_fade_out_in",
    "raw_echo_drop",
    "raw_lp_swap",
)


@dataclass(frozen=True)
class TransitionEdge:
    from_track_id: str
    to_track_id: str

    transition_score: float
    technical_score: float
    musical_score: float
    performance_score: float
    risk_score: float
    risk_level: str  # A / B / C / D

    allowed_rules: list[str]
    forbidden_rules: list[str]
    best_rule: str
    reason: str

    energy_delta: float            # B_entry_window - A_exit_window
    bpm_delta: float               # B.bpm - A.bpm
    vocal_conflict: bool
    low_end_conflict: bool
    key_compatible: bool

    exit_time: float               # chosen exit point on A
    entry_time: float              # chosen entry point on B

    def as_dict(self) -> dict:
        return {
            "from": self.from_track_id,
            "to": self.to_track_id,
            "score": round(self.transition_score, 3),
            "technical": round(self.technical_score, 3),
            "musical": round(self.musical_score, 3),
            "performance": round(self.performance_score, 3),
            "risk": round(self.risk_score, 3),
            "risk_level": self.risk_level,
            "allowed_rules": list(self.allowed_rules),
            "forbidden_rules": list(self.forbidden_rules),
            "best_rule": self.best_rule,
            "reason": self.reason,
            "energy_delta": round(self.energy_delta, 3),
            "bpm_delta": round(self.bpm_delta, 2),
            "vocal_conflict": self.vocal_conflict,
            "low_end_conflict": self.low_end_conflict,
            "key_compatible": self.key_compatible,
            "exit_time": round(self.exit_time, 3),
            "entry_time": round(self.entry_time, 3),
        }


# ----- Camelot helpers ----------------------------------------------------

def _parse_camelot(camelot: str | None) -> tuple[int, str] | None:
    """'8A' -> (8, 'A'). Returns None if unparseable."""
    if not camelot:
        return None
    s = str(camelot).strip().upper()
    if len(s) < 2 or s[-1] not in ("A", "B"):
        return None
    try:
        n = int(s[:-1])
        if 1 <= n <= 12:
            return n, s[-1]
    except ValueError:
        return None
    return None


def _camelot_compatible(a: str | None, b: str | None) -> tuple[bool, float]:
    """Return (compatible_bool, score 0..1) per Camelot wheel rules.

    Ideal:    same key                       → 1.00
    Good:     ±1 same letter / same n flip   → 0.85
    OK:       ±2 same letter                 → 0.65
    Bad:      else                           → 0.30
    Unknown:  one missing                    → 0.55 (neutral)
    """
    pa = _parse_camelot(a)
    pb = _parse_camelot(b)
    if pa is None or pb is None:
        return True, 0.55
    na, la = pa
    nb, lb = pb
    if na == nb and la == lb:
        return True, 1.0
    if la == lb:
        diff = min((na - nb) % 12, (nb - na) % 12)
        if diff == 1:
            return True, 0.85
        if diff == 2:
            return True, 0.65
    if na == nb and la != lb:
        return True, 0.85
    return False, 0.30


# ----- Window helpers -----------------------------------------------------

def _exit_window(profile: TrackProfile) -> tuple[float, SectionEnergy | None]:
    """Pick the most musically-sane exit point + the section covering it."""
    if profile.safe_exit_points:
        # Prefer an exit that's NOT inside the last 6 seconds
        candidates = [t for t in profile.safe_exit_points if t < profile.duration - 3.0]
        t = candidates[-1] if candidates else profile.safe_exit_points[-1]
    else:
        t = max(0.0, profile.duration - 8.0)
    sec = profile.windows_around(t, window_sec=8.0)
    return t, sec


def _entry_window(profile: TrackProfile) -> tuple[float, SectionEnergy | None]:
    """Pick the first phrase-aligned entry; fallback to first downbeat."""
    if profile.safe_entry_points:
        t = profile.safe_entry_points[0]
    elif profile.downbeats:
        t = next((float(d) for d in profile.downbeats if d > 1.0), float(profile.downbeats[0]))
    else:
        t = 0.0
    sec = profile.windows_around(t, window_sec=8.0)
    return t, sec


# ----- Per-dimension scorers ---------------------------------------------

def _bpm_lane_fit(a_bpm: float, b_bpm: float) -> float:
    """Same lane = perfect; ±3% = great; ±6% = OK with stretch; >10% = bad."""
    if a_bpm <= 0 or b_bpm <= 0:
        return 0.4
    ratio = abs(b_bpm - a_bpm) / max(a_bpm, b_bpm)
    if ratio <= 0.005:
        return 1.0
    if ratio <= 0.03:
        return 0.90
    if ratio <= 0.06:
        return 0.75
    if ratio <= 0.10:
        return 0.55
    return max(0.0, 1.0 - ratio * 5.0)


def _technical_score(a: TrackProfile, b: TrackProfile,
                     key_score: float) -> float:
    """BPM lane × Camelot × beat_confidence × stems."""
    bpm_fit = _bpm_lane_fit(a.bpm, b.bpm)
    confidence = 0.5 * (a.beat_confidence + b.beat_confidence)
    stems_bonus = 1.0 if (a.stems_available and b.stems_available) else 0.7
    return float(0.45 * bpm_fit + 0.25 * key_score + 0.20 * confidence + 0.10 * stems_bonus)


def _musical_score(a_exit: SectionEnergy | None, b_entry: SectionEnergy | None,
                   vocal_conflict: bool, low_end_conflict: bool) -> tuple[float, float]:
    """Returns (score, energy_delta).

    Energy_delta = B_entry.dance - A_exit.dance.
    Penalize big drops/jumps and vocal/low-end conflicts.
    """
    if a_exit is None or b_entry is None:
        return 0.5, 0.0
    delta = b_entry.section_dance_energy - a_exit.section_dance_energy
    # Smooth around 0 (perfect match), allow +0.2 build, -0.15 release
    if delta >= 0:
        delta_fit = 1.0 - min(1.0, max(0.0, delta - 0.20) / 0.40)
    else:
        delta_fit = 1.0 - min(1.0, max(0.0, -delta - 0.15) / 0.45)
    impact_fit = 1.0 - min(1.0, abs(b_entry.section_impact_energy - a_exit.section_impact_energy) / 0.6)
    groove_fit = 1.0 - min(1.0, abs(b_entry.section_groove_energy - a_exit.section_groove_energy) / 0.6)
    penalty = 0.0
    if vocal_conflict:
        penalty += 0.20
    if low_end_conflict:
        penalty += 0.15
    score = 0.50 * delta_fit + 0.30 * impact_fit + 0.20 * groove_fit - penalty
    return float(max(0.0, min(1.0, score))), float(delta)


def _performance_score(a: TrackProfile, b: TrackProfile,
                       a_exit_sec: SectionEnergy | None,
                       b_entry_sec: SectionEnergy | None) -> float:
    """How clean does this transition feel to perform live?

    - groove tightness on both sides of the seam
    - safe-entry / safe-exit availability
    - section being a stable region (not a 'build' that we'd cut mid-rise)
    """
    a_groove = a_exit_sec.section_groove_energy if a_exit_sec else a.groove_tightness
    b_groove = b_entry_sec.section_groove_energy if b_entry_sec else b.groove_tightness
    groove_avg = 0.5 * (a_groove + b_groove)
    safe_exit_bonus = 1.0 if a.safe_exit_points else 0.6
    safe_entry_bonus = 1.0 if b.safe_entry_points else 0.6
    # Penalize cutting out of a 'build' section (tension still rising)
    a_label = (a_exit_sec.label if a_exit_sec else "").lower()
    build_penalty = 0.15 if a_label in {"build", "drop"} else 0.0
    score = 0.45 * groove_avg + 0.30 * safe_exit_bonus + 0.25 * safe_entry_bonus - build_penalty
    return float(max(0.0, min(1.0, score)))


def _detect_vocal_conflict(a_exit: SectionEnergy | None,
                           b_entry: SectionEnergy | None) -> bool:
    """Both sides vocal-heavy at the seam → vocal stack."""
    if a_exit is None or b_entry is None:
        return False
    return a_exit.section_vocal_density >= 0.55 and b_entry.section_vocal_density >= 0.55


def _detect_low_end_conflict(a_exit: SectionEnergy | None,
                             b_entry: SectionEnergy | None) -> bool:
    """Both sides have heavy bass + kick → mud."""
    if a_exit is None or b_entry is None:
        return False
    a_low = 0.5 * (a_exit.section_kick_punch + a_exit.section_low_mid_density)
    b_low = 0.5 * (b_entry.section_kick_punch + b_entry.section_low_mid_density)
    return a_low >= 0.65 and b_low >= 0.65


def _risk_score(technical: float, musical: float,
                vocal_conflict: bool, low_end_conflict: bool,
                bpm_delta_pct: float, key_compatible: bool) -> float:
    """1.0 = no risk. Each hard conflict subtracts.

    Hard risks:
      - BPM drift > 10%        : -0.35
      - Key incompatible       : -0.20
      - Vocal conflict         : -0.15
      - Low-end conflict       : -0.15
      - technical < 0.50       : -0.20
      - musical   < 0.40       : -0.15
    """
    risk = 1.0
    if bpm_delta_pct > 0.10:
        risk -= 0.35
    elif bpm_delta_pct > 0.06:
        risk -= 0.10
    if not key_compatible:
        risk -= 0.20
    if vocal_conflict:
        risk -= 0.15
    if low_end_conflict:
        risk -= 0.15
    if technical < 0.50:
        risk -= 0.20
    if musical < 0.40:
        risk -= 0.15
    return float(max(0.0, min(1.0, risk)))


def _risk_level(score: float) -> str:
    if score >= 0.85:
        return "A"
    if score >= 0.75:
        return "B"
    if score >= 0.60:
        return "C"
    return "D"


# ----- Rule selection -----------------------------------------------------

def _rule_eligibility(a: TrackProfile, b: TrackProfile,
                      a_exit: SectionEnergy | None,
                      b_entry: SectionEnergy | None,
                      vocal_conflict: bool,
                      low_end_conflict: bool,
                      bpm_delta_pct: float,
                      key_compatible: bool) -> tuple[list[str], list[str]]:
    """Eligibility table for the 18 mixer_rules keys.

    Returns (allowed, forbidden). Pure availability filter — _pick_best_rule
    chooses among allowed[] using musical context.
    """
    allowed: list[str] = []
    forbidden: list[str] = []

    has_stems = a.stems_available and b.stems_available
    a_label = (a_exit.label if a_exit else "").lower()
    b_label = (b_entry.label if b_entry else "").lower()
    a_kick = a_exit.section_kick_punch if a_exit else a.kick_punch
    b_kick = b_entry.section_kick_punch if b_entry else b.kick_punch
    both_analyzed = (a.bpm > 0 and b.bpm > 0
                     and bool(a.beat_points) and bool(b.beat_points))

    # ---- 11 ANALYZED (need bpm + beat grid) ----
    if both_analyzed:
        # harmonic_blend — 16-bar blend, key-compat + BPM lane
        if key_compatible and bpm_delta_pct <= 0.04:
            allowed.append("harmonic_blend")
        else:
            forbidden.append("harmonic_blend")

        # eq_swap_4bar — workhorse blend
        if bpm_delta_pct <= 0.08 and not (vocal_conflict and low_end_conflict):
            allowed.append("eq_swap_4bar")
        else:
            forbidden.append("eq_swap_4bar")

        # filter_sweep_high — masks medium BPM/key drift
        if 0.02 <= bpm_delta_pct <= 0.10 or not key_compatible:
            allowed.append("filter_sweep_high")

        # drop_swap — bass-pivot smash; needs B kick + ideally stems
        if b_kick >= 0.55 and a_kick >= 0.45:
            allowed.append("drop_swap")
        else:
            forbidden.append("drop_swap")

        # echo_tail — soft outro, energy step-down friendly
        allowed.append("echo_tail")

        # loop_roll — 8th-roll over 2 bars; tempo close
        if bpm_delta_pct <= 0.06 and a.beat_confidence >= 0.45:
            allowed.append("loop_roll")
        else:
            forbidden.append("loop_roll")

        # spin_back — bold tempo break
        if bpm_delta_pct >= 0.10 or not key_compatible:
            allowed.append("spin_back")

        # drum_only_bridge — needs stems on both
        if has_stems and a.beat_confidence >= 0.45 and b.beat_confidence >= 0.45:
            allowed.append("drum_only_bridge")
        else:
            forbidden.append("drum_only_bridge")

        # key_lift — +1 semitone ride
        if bpm_delta_pct <= 0.08:
            allowed.append("key_lift")

        # reverb_throw — wet tail, energy down
        allowed.append("reverb_throw")

        # back_to_back_drop — smash cut on downbeat
        if b_kick >= 0.55:
            allowed.append("back_to_back_drop")
        else:
            forbidden.append("back_to_back_drop")
    else:
        for r in ("harmonic_blend", "eq_swap_4bar", "filter_sweep_high",
                  "drop_swap", "echo_tail", "loop_roll", "spin_back",
                  "drum_only_bridge", "key_lift", "reverb_throw",
                  "back_to_back_drop"):
            forbidden.append(r)

    # ---- 7 RAW (no analysis required) — always available as fallback ----
    allowed.extend([
        "raw_xfade_3s", "raw_xfade_6s", "raw_xfade_10s",
        "raw_hard_cut", "raw_fade_out_in", "raw_echo_drop", "raw_lp_swap",
    ])

    return allowed, forbidden


def _pick_best_rule(allowed: list[str], a: TrackProfile, b: TrackProfile,
                    a_exit: SectionEnergy | None, b_entry: SectionEnergy | None,
                    energy_delta: float,
                    vocal_conflict: bool, low_end_conflict: bool) -> tuple[str, str]:
    """Pick the most musical rule from allowed[] using section context.

    Returns (rule_key, reason). rule_key is one of mixer_rules.py's 18 keys.
    Falls back to a RAW rule when no ANALYZED rule fits.
    """
    has_stems = a.stems_available and b.stems_available
    bpm_diff_pct = abs(b.bpm - a.bpm) / max(a.bpm, b.bpm) if a.bpm > 0 and b.bpm > 0 else 1.0
    a_label = (a_exit.label if a_exit else "").lower()

    def pick(rule: str, reason: str) -> tuple[str, str] | None:
        return (rule, reason) if rule in allowed else None

    # 1) Vocal conflict — bridge through drums-only
    if vocal_conflict:
        r = pick("drum_only_bridge", "两端人声叠加，drum_only_bridge 让 A.drums 撑过桥段")
        if r: return r
        r = pick("filter_sweep_high", "两端人声叠加，高通扫频遮蔽 A 人声")
        if r: return r

    # 2) Low-end conflict — drum_only_bridge or bass-swap drop
    if low_end_conflict:
        r = pick("drum_only_bridge", "两端低频都重，drum_only_bridge 让 B 接管低频")
        if r: return r
        r = pick("drop_swap", "低频冲突，drop_swap 在 downbeat 上互换 bass")
        if r: return r

    # 3) Big positive energy jump → drop / smash
    if energy_delta >= 0.18:
        r = pick("drop_swap", "B 入歌点能量大幅上扬，drop_swap 制造爆点")
        if r: return r
        r = pick("back_to_back_drop", "能量上扬，back_to_back_drop 在 downbeat 硬切")
        if r: return r
        r = pick("key_lift", "能量上扬，key_lift +1 半音衔接")
        if r: return r

    # 4) Big negative energy jump → soft outro
    if energy_delta <= -0.18:
        r = pick("echo_tail", "B 入歌点能量大幅下降，echo_tail 软落")
        if r: return r
        r = pick("reverb_throw", "能量下降，reverb_throw 湿尾收束")
        if r: return r

    # 5) Build / drop label on A → loop_roll
    if a_label in {"build", "drop"}:
        r = pick("loop_roll", "A 处于 build/drop，loop_roll 收束后落 B")
        if r: return r

    # 6) Tempo far apart → spin_back
    if bpm_diff_pct >= 0.10:
        r = pick("spin_back", "BPM 差距大，spin_back 制造 tempo 切断")
        if r: return r

    # 7) Smooth segments → harmonic_blend / eq_swap
    if abs(energy_delta) <= 0.10:
        r = pick("harmonic_blend", "Camelot 兼容、能量平稳 → 16-bar harmonic_blend")
        if r: return r
    r = pick("eq_swap_4bar", "标准 4-bar EQ swap")
    if r: return r
    r = pick("filter_sweep_high", "高通扫频，掩盖 BPM/key 漂移")
    if r: return r

    # 8) RAW fallback — pick by energy delta
    if energy_delta <= -0.18:
        r = pick("raw_fade_out_in", "RAW: fade-out-in 处理大能量降")
        if r: return r
        r = pick("raw_echo_drop", "RAW: 回声衔接")
        if r: return r
    if abs(energy_delta) <= 0.10:
        r = pick("raw_xfade_6s", "RAW: 6 秒交叉淡入")
        if r: return r
    r = pick("raw_xfade_3s", "RAW: 3 秒交叉淡入")
    if r: return r
    r = pick("raw_hard_cut", "RAW fallback: 硬切")
    if r: return r
    return allowed[0] if allowed else "raw_hard_cut", "fallback"


# ----- Main entry ---------------------------------------------------------

def analyze_edge(a: TrackProfile, b: TrackProfile) -> TransitionEdge:
    """Full pairwise transition edge analysis."""
    exit_t, a_exit = _exit_window(a)
    entry_t, b_entry = _entry_window(b)

    bpm_delta = b.bpm - a.bpm
    bpm_delta_pct = abs(bpm_delta) / max(a.bpm, b.bpm) if a.bpm > 0 and b.bpm > 0 else 1.0
    key_compatible, key_score = _camelot_compatible(a.camelot_key, b.camelot_key)

    vocal_conflict = _detect_vocal_conflict(a_exit, b_entry)
    low_end_conflict = _detect_low_end_conflict(a_exit, b_entry)

    technical = _technical_score(a, b, key_score)
    musical, energy_delta = _musical_score(a_exit, b_entry, vocal_conflict, low_end_conflict)
    performance = _performance_score(a, b, a_exit, b_entry)
    risk = _risk_score(technical, musical, vocal_conflict, low_end_conflict,
                       bpm_delta_pct, key_compatible)

    transition = 0.30 * technical + 0.30 * musical + 0.20 * performance + 0.20 * risk
    transition = float(max(0.0, min(1.0, transition)))
    risk_level = _risk_level(transition)

    allowed, forbidden = _rule_eligibility(a, b, a_exit, b_entry,
                                           vocal_conflict, low_end_conflict,
                                           bpm_delta_pct, key_compatible)
    best_rule, reason = _pick_best_rule(allowed, a, b, a_exit, b_entry,
                                        energy_delta, vocal_conflict, low_end_conflict)

    return TransitionEdge(
        from_track_id=a.track_id,
        to_track_id=b.track_id,
        transition_score=transition,
        technical_score=technical,
        musical_score=musical,
        performance_score=performance,
        risk_score=risk,
        risk_level=risk_level,
        allowed_rules=allowed,
        forbidden_rules=forbidden,
        best_rule=best_rule,
        reason=reason,
        energy_delta=energy_delta,
        bpm_delta=bpm_delta,
        vocal_conflict=vocal_conflict,
        low_end_conflict=low_end_conflict,
        key_compatible=key_compatible,
        exit_time=exit_t,
        entry_time=entry_t,
    )


def analyze_all_edges(profiles: list[TrackProfile]) -> dict[tuple[str, str], TransitionEdge]:
    """Pairwise analysis for all directed (A, B) where A != B."""
    out: dict[tuple[str, str], TransitionEdge] = {}
    for a in profiles:
        for b in profiles:
            if a.track_id == b.track_id:
                continue
            out[(a.track_id, b.track_id)] = analyze_edge(a, b)
    return out
