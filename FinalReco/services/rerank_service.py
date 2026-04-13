from typing import List

import numpy as np

from services.clap_service import encode_texts, normalize


def rerank_tracks(vibe_description: str, tracks: List[dict]) -> List[dict]:
    if not tracks:
        return []

    query_vector = normalize(encode_texts([vibe_description])[0])
    candidate_texts = []
    for track in tracks:
        name = str(track.get("name") or track.get("track_name") or "")
        artists_data = track.get("artists") or []
        if artists_data and isinstance(artists_data[0], dict):
            artists = ", ".join(str((artist or {}).get("name") or "") for artist in artists_data)
        else:
            artists = str(track.get("artist") or "")
        candidate_texts.append(" ".join(part for part in [name, artists] if part).strip())

    candidate_embeddings = encode_texts(candidate_texts)
    scored = []
    for track, embedding in zip(tracks, candidate_embeddings):
        score = float(np.dot(query_vector, normalize(embedding)))
        enriched = dict(track)
        enriched["semantic_score"] = score
        scored.append((score, enriched))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [track for _, track in scored]
