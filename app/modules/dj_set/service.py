"""DJ Set service — top-level orchestrator.

Inputs: list of LibrarySong (already authorized by caller).
Outputs: list[DJSet] (one per template, sorted by quality-adjusted score).

This is the function the /set/generate router endpoint calls.
"""
from __future__ import annotations

from dataclasses import replace

from app.modules.dj_set.edge_analyzer import analyze_all_edges
from app.modules.dj_set.purpose_planner import plan_purposes
from app.modules.dj_set.quality_gate import evaluate_quality
from app.modules.dj_set.role_classifier import classify_track
from app.modules.dj_set.set_optimizer import DJSet, optimize_all_templates
from app.modules.dj_set.set_templates import ALL_TEMPLATES, get_template
from app.modules.dj_set.track_profiler import build_track_profile
from app.modules.dj_set.transition_plan import build_all_plans


def generate_dj_sets(songs: list,
                     *,
                     templates: list | None = None,
                     beam_width: int = 12,
                     drop_failed: bool = True) -> dict:
    """Top-level pipeline.

    Returns:
        {
          "profiles":   list[dict]   # per song, summary
          "roles":      list[dict]   # per song, role assessment
          "edges":      list[dict]   # all pairwise edges (full matrix is small)
          "sets":       list[dict]   # one per template, sorted desc by score+quality
        }
    """
    if not songs:
        return {"profiles": [], "roles": [], "edges": [], "sets": []}

    # Map LibrarySong (or test namespace) by str(id) so plan builder can
    # delegate spec generation to mixer_rules.build_transition_spec.
    songs_by_id = {str(getattr(s, "id", "")): s for s in songs}

    # 1) Profiles
    profiles = [build_track_profile(s) for s in songs]
    profiles_by_id = {p.track_id: p for p in profiles}

    # 2) Roles
    role_map = {p.track_id: classify_track(p) for p in profiles}

    # 3) Edges
    edges = analyze_all_edges(profiles)

    # 4-6) Per template: optimize + tag purposes + build plans + quality gate
    selected_templates = templates or list(ALL_TEMPLATES)
    raw_sets = optimize_all_templates(profiles, role_map, edges,
                                      selected_templates, beam_width=beam_width)

    out_sets: list[dict] = []
    for ds in raw_sets:
        purposes = plan_purposes(ds, role_map)
        plans = build_all_plans(ds.transitions, purposes, songs_by_id)
        tpl = get_template(ds.template_name)
        report = evaluate_quality(ds, tpl, role_map, profiles_by_id)
        if drop_failed and not report.passed:
            continue
        adjusted_score = float(max(0.0, ds.score + report.score_delta))
        out_sets.append({
            **ds.as_dict(),
            "adjusted_score": round(adjusted_score, 3),
            "quality": report.as_dict(),
            "purposes": [p.as_dict() for p in purposes],
            "plans": [p.as_dict() for p in plans],
        })

    out_sets.sort(key=lambda d: d.get("adjusted_score", 0.0), reverse=True)

    return {
        "profiles": [
            {
                "track_id": p.track_id,
                "title": p.title,
                "artist": p.artist,
                "duration": p.duration,
                "bpm": p.bpm,
                "camelot_key": p.camelot_key,
                "dance_energy": round(p.dance_energy, 3),
                "vocal_density": round(p.vocal_density, 3),
                "groove_energy": round(p.groove_energy, 3),
                "impact_energy": round(p.impact_energy, 3),
                "stems_available": p.stems_available,
                "section_count": len(p.sections),
            }
            for p in profiles
        ],
        "roles": [role_map[p.track_id].as_dict() for p in profiles],
        "edges": [e.as_dict() for e in edges.values()],
        "sets": out_sets,
    }


def preview_transition(prev_song, next_song) -> dict:
    """Build a one-pair preview: edge + purpose + plan."""
    a = build_track_profile(prev_song)
    b = build_track_profile(next_song)
    role_map = {a.track_id: classify_track(a), b.track_id: classify_track(b)}
    edges = analyze_all_edges([a, b])
    edge = edges.get((a.track_id, b.track_id))
    if edge is None:
        return {"error": "no edge between these tracks"}
    # Build a minimal DJSet so we can reuse plan_purposes / build_all_plans.
    fake_set = DJSet(
        template_name="preview",
        ordered_tracks=[a.track_id, b.track_id],
        transitions=[edge],
        score=edge.transition_score,
        score_breakdown={},
        narrative_arc=[role_map[a.track_id].primary_role,
                       role_map[b.track_id].primary_role],
        energy_curve=[a.dance_energy, b.dance_energy],
        warnings=[],
    )
    purposes = plan_purposes(fake_set, role_map)
    songs_by_id = {a.track_id: prev_song, b.track_id: next_song}
    plans = build_all_plans(fake_set.transitions, purposes, songs_by_id)
    return {
        "edge": edge.as_dict(),
        "purpose": purposes[0].as_dict() if purposes else None,
        "plan": plans[0].as_dict() if plans else None,
        "from": {"track_id": a.track_id, "title": a.title, "bpm": a.bpm,
                 "dance_energy": round(a.dance_energy, 3)},
        "to":   {"track_id": b.track_id, "title": b.title, "bpm": b.bpm,
                 "dance_energy": round(b.dance_energy, 3)},
    }
