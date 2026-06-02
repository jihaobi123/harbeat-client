"""External metadata enrichment and style-score persistence."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.modules.dj_control.dance_style import STYLE_PROFILES, compute_manual_feedback_score, compute_mixability_score, score_song_combined
from app.modules.library.external_metadata.clients import fetch_all_external_metadata
from app.modules.library.external_metadata.normalizer import normalize_labels
from app.modules.library.external_metadata.schemas import ExternalEnrichmentResult, ExternalSourceResult
from app.modules.library.external_metadata.scorer import (
    clamp01,
    fuse_external_source_scores,
    fuse_final_style_score,
    normalize_weights,
    score_external_tags_for_style,
)
from app.shared.config import get_settings

logger = logging.getLogger(__name__)

FetchFn = Callable[..., object]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _cache_fresh(song, ttl_days: int) -> bool:
    gp = getattr(song, "genre_profile", None) or {}
    if not isinstance(gp, dict) or not gp.get("style_evidence_v1"):
        return False
    sources = gp.get("sources") or {}
    fetched = []
    for payload in sources.values() if isinstance(sources, dict) else []:
        if isinstance(payload, dict):
            ts = _parse_iso(payload.get("fetched_at"))
            if ts:
                fetched.append(ts)
    if not fetched:
        return False
    newest = max(fetched)
    return newest >= datetime.now(timezone.utc) - timedelta(days=max(1, ttl_days))


def _local_source_labels(song) -> list[str]:
    labels: list[str] = []
    gp = getattr(song, "genre_profile", None) or {}
    if isinstance(gp, dict):
        if gp.get("primary_genre"):
            labels.append(str(gp["primary_genre"]))
        for item in gp.get("genres") or []:
            if isinstance(item, dict) and item.get("name"):
                labels.append(str(item["name"]))
    dfp = getattr(song, "dancefloor_profile", None) or {}
    if isinstance(dfp, dict):
        for key in ("mood", "groove", "density"):
            if dfp.get(key):
                labels.append(str(dfp[key]))
    return normalize_labels(labels)


def _score_from_source(style: str, source: ExternalSourceResult) -> float | None:
    if source.status != "hit":
        return None
    return score_external_tags_for_style(
        source.normalized_labels(),
        style,
        source_confidence=source.confidence,
    )


def _manual_score(style: str, song) -> float | None:
    component = compute_manual_feedback_score(style, song)
    if component.get("score") is None or component.get("available") is False:
        return None
    return clamp01(component.get("score"))


def _tunable_score(song) -> float | None:
    component = compute_mixability_score(song)
    if component.get("score") is None or component.get("available") is False:
        return None
    return clamp01(component.get("score"))


def _status_from_sources(sources: dict[str, ExternalSourceResult], has_local: bool) -> str:
    hits = [s for s in sources.values() if s.status == "hit"]
    enabled = [s for s in sources.values() if s.status != "disabled"]
    if hits:
        return "ready"
    if has_local:
        return "partial" if enabled else "local_only"
    return "needs_review"


def _source_reason(source_name: str, source: ExternalSourceResult, labels: list[str]) -> str | None:
    if source.status != "hit" or not labels:
        return None
    return f"{source_name} 命中 " + " / ".join(labels[:4])


async def enrich_song_external_metadata(
    db: Session,
    song,
    *,
    force: bool = False,
    timeout_sec: float | None = None,
    fetcher: FetchFn | None = None,
    commit: bool = True,
) -> ExternalEnrichmentResult:
    settings = get_settings()
    timeout = float(timeout_sec or settings.external_style_timeout_sec or 8.0)
    gp = dict(getattr(song, "genre_profile", None) or {})

    if not force and _cache_fresh(song, int(settings.external_style_cache_ttl_days or 30)):
        sources = {
            name: ExternalSourceResult(
                source=name,
                status=str(payload.get("status") or "cached"),
                labels=list(payload.get("raw_labels") or payload.get("labels") or []),
                confidence=float(payload.get("confidence", 0.0) or 0.0),
                raw=dict(payload.get("raw") or {}),
            )
            for name, payload in (gp.get("sources") or {}).items()
            if isinstance(payload, dict)
        }
        return ExternalEnrichmentResult(
            song_id=str(getattr(song, "id", "")),
            sources=sources,
            style_evidence=dict(gp.get("style_evidence_v1") or {}),
            dance_style_scores=dict(getattr(song, "dance_style_scores", {}) or {}),
            status=str(getattr(song, "dance_style_status", "ready") or "ready"),
        )

    if settings.enable_external_style_enrichment:
        try:
            if fetcher is None:
                sources = await fetch_all_external_metadata(
                    title=str(getattr(song, "title", "") or ""),
                    artist=str(getattr(song, "artist", "") or ""),
                    timeout_sec=timeout,
                )
            else:
                maybe = fetcher(title=getattr(song, "title", ""), artist=getattr(song, "artist", ""), timeout_sec=timeout)
                sources = await maybe if hasattr(maybe, "__await__") else maybe
        except Exception:
            logger.exception("[style-enrich] external fetch failed for song %s", getattr(song, "id", ""))
            sources = {
                "musicbrainz": ExternalSourceResult.error_result("musicbrainz", "fetch failed"),
                "lastfm": ExternalSourceResult.error_result("lastfm", "fetch failed"),
                "discogs": ExternalSourceResult.error_result("discogs", "fetch failed"),
            }
    else:
        sources = {
            "musicbrainz": ExternalSourceResult.disabled("musicbrainz", "feature_disabled"),
            "lastfm": ExternalSourceResult.disabled("lastfm", "feature_disabled"),
            "discogs": ExternalSourceResult.disabled("discogs", "feature_disabled"),
        }

    source_payloads = {
        name: source.as_genre_profile_source()
        for name, source in sources.items()
    }
    local_labels = _local_source_labels(song)
    source_payloads["local"] = {
        "status": "hit" if local_labels else "miss",
        "labels": local_labels,
        "confidence": 0.70 if local_labels else 0.0,
        "version": "audio_genre_profile_v1",
    }

    source_weights = normalize_weights({
        "discogs": settings.style_external_weight_discogs,
        "lastfm": settings.style_external_weight_lastfm,
        "musicbrainz": settings.style_external_weight_musicbrainz,
    })
    final_weights = normalize_weights({
        "external": settings.style_score_weight_external,
        "local": settings.style_score_weight_local,
        "manual": settings.style_score_weight_manual,
        "tunable": settings.style_score_weight_tunable,
    })

    style_evidence: dict[str, dict] = {}
    scores: dict[str, float] = {}
    ranked: list[dict] = []
    tunable = _tunable_score(song)
    has_local = False
    for style in STYLE_PROFILES:
        local_score, local_version, local_breakdown = score_song_combined(song, style)
        has_local = has_local or local_score > 0
        per_source_scores = {
            source_name: _score_from_source(style, source)
            for source_name, source in sources.items()
        }
        external_score = fuse_external_source_scores(per_source_scores, source_weights)
        manual = _manual_score(style, song)
        final = fuse_final_style_score(
            external_platform_score=external_score,
            local_fingerprint_score=local_score,
            manual_style_score=manual,
            tunable_adjustment_score=tunable,
            weights=final_weights,
        )
        status = _status_from_sources(sources, has_local=local_score > 0)
        reasons: list[str] = []
        for source_name in ("discogs", "lastfm", "musicbrainz"):
            source = sources.get(source_name)
            if not source:
                continue
            matched = [
                label for label in source.normalized_labels()
                if score_external_tags_for_style([label], style, source.confidence) >= 0.45
            ]
            reason = _source_reason(source_name, source, matched)
            if reason:
                reasons.append(reason)
        if local_score > 0:
            reasons.append(f"本地 fingerprint {local_version} 分数 {local_score:.2f}")
        style_evidence[style] = {
            "external_platform_score": external_score,
            "local_fingerprint_score": round(clamp01(local_score), 4),
            "manual_style_score": manual,
            "tunable_adjustment_score": tunable,
            "final_score": final,
            "confidence": round(max(
                [s.confidence for s in sources.values() if s.status == "hit"] + [0.55 if local_score > 0 else 0.0]
            ), 4),
            "status": status,
            "weights": {
                "external": final_weights.get("external", 0.0),
                "local": final_weights.get("local", 0.0),
                "manual": final_weights.get("manual", 0.0),
                "tunable": final_weights.get("tunable", 0.0),
            },
            "external_source_scores": per_source_scores,
            "local_version": local_version,
            "local_breakdown": local_breakdown,
            "reason": reasons[:6],
        }
        scores[style] = final
        ranked.append({
            "style": style,
            "score": final,
            "source": "style_evidence_v1",
            "confidence": style_evidence[style]["confidence"],
            "breakdown": {
                "external_platform_score": external_score,
                "local_fingerprint_score": round(clamp01(local_score), 4),
                "manual_style_score": manual,
                "tunable_adjustment_score": tunable,
            },
        })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    gp["sources"] = source_payloads
    gp["style_evidence_v1"] = style_evidence
    song.genre_profile = gp
    song.dance_style_scores = scores
    song.dance_styles = ranked
    song.dance_style_status = _status_from_sources(sources, has_local=has_local)
    db.add(song)
    if commit:
        db.commit()
        try:
            db.refresh(song)
        except Exception:
            pass
    return ExternalEnrichmentResult(
        song_id=str(getattr(song, "id", "")),
        sources=sources,
        style_evidence=style_evidence,
        dance_style_scores=scores,
        status=song.dance_style_status,
    )


def run_enrich_song_external_metadata(
    db: Session,
    song,
    *,
    force: bool = False,
    timeout_sec: float | None = None,
    fetcher: FetchFn | None = None,
    commit: bool = True,
) -> ExternalEnrichmentResult:
    return asyncio.run(
        enrich_song_external_metadata(
            db,
            song,
            force=force,
            timeout_sec=timeout_sec,
            fetcher=fetcher,
            commit=commit,
        )
    )

