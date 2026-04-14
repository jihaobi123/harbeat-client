from typing import Dict, List, Tuple

import numpy as np
import streamlit as st
import torch
from transformers import AutoModel, AutoProcessor


TRANSLATION_HINTS: Dict[str, str] = {
    "雨夜": "rainy midnight atmosphere",
    "忧郁": "melancholic introspective mood",
    "伤感": "sad reflective feeling",
    "霓虹": "neon city glow",
    "独自": "solitary and intimate",
    "漫步": "slow drifting motion",
    "驾驶": "night driving pulse",
    "老派": "old school character",
    "爵士": "jazz-influenced harmony",
    "嘻哈": "hip-hop groove",
}

GENRE_KEYWORDS = {
    "hip-hop": ["hip hop", "hip-hop", "hiphop", "rap", "boom bap", "old school", "嘻哈"],
    "jazz": ["jazz", "jazzhop", "爵士", "sax"],
    "electronic": ["electronic", "synth", "edm", "neon", "赛博"],
    "ambient": ["ambient", "atmospheric", "drone", "rainy", "雨夜"],
    "rock": ["rock", "guitar", "band", "alt rock"],
    "indie": ["indie", "lofi", "lo-fi", "bedroom"],
    "acoustic": ["acoustic", "unplugged", "folk", "singer-songwriter"],
    "soul": ["soul", "r&b", "rnb", "motown"],
    "pop": ["pop", "radio", "mainstream"],
    "blues": ["blues", "delta blues"],
}


@st.cache_resource(show_spinner="Loading CLAP semantic model...")
def load_clap_model() -> Tuple[AutoProcessor, AutoModel]:
    model_id = "laion/clap-htsat-unfused"
    try:
        processor = AutoProcessor.from_pretrained(model_id, local_files_only=True)
        model = AutoModel.from_pretrained(model_id, local_files_only=True)
    except Exception:
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModel.from_pretrained(model_id)
    model.eval()
    return processor, model


@torch.inference_mode()
def encode_texts(texts: List[str]) -> np.ndarray:
    processor, model = load_clap_model()
    inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True)
    features = model.get_text_features(**inputs)

    if hasattr(features, "pooler_output") and features.pooler_output is not None:
        array = features.pooler_output.detach().cpu().numpy()
    elif torch.is_tensor(features):
        array = features.detach().cpu().numpy()
    else:
        array = np.asarray(features)

    return array.reshape(len(texts), -1)


def _normalize(vector: np.ndarray) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-8)


def _extract_year_filter(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["90s", "1990", "199", "九十"]):
        return "year:1990-2005"
    if any(token in lowered for token in ["80s", "1980", "198", "八十"]):
        return "year:1980-1995"
    if any(token in lowered for token in ["2000s", "2000", "千禧"]):
        return "year:2000-2015"
    return ""


def _extract_genres(text: str) -> List[str]:
    lowered = text.lower()
    scored: List[tuple[int, str]] = []
    for genre, keys in GENRE_KEYWORDS.items():
        score = sum(1 for key in keys if key in lowered)
        if score > 0:
            scored.append((score, genre))

    scored.sort(reverse=True)
    genres = [genre for _, genre in scored[:2]]
    return genres or ["electronic"]


def _build_vibe_description(text: str) -> str:
    hints = [value for key, value in TRANSLATION_HINTS.items() if key in text]
    base = text.strip()
    if hints:
        return f"{base}. Vibe cues: {', '.join(hints)}."
    return base


def interpret_vibe(text: str) -> Dict[str, str]:
    genres = _extract_genres(text)
    year_filter = _extract_year_filter(text)

    # Keep query strict and stable: only genre/year advanced tokens.
    query_core = f"genre:{genres[0]}"
    search_query = f"{query_core} {year_filter}".strip()
    vibe_description = _build_vibe_description(text)

    return {
        "search_query": search_query,
        "vibe_description": vibe_description,
    }


def rerank(vibe_description: str, tracks: List[dict]) -> List[dict]:
    if not tracks:
        return []

    query_vector = _normalize(encode_texts([vibe_description])[0])

    candidate_texts: List[str] = []
    for track in tracks:
        name = str(track.get("name") or "")
        artists = ", ".join(
            str((artist or {}).get("name") or "")
            for artist in (track.get("artists") or [])
        )
        candidate_texts.append(" ".join(part for part in [name, artists] if part).strip())

    candidate_embeddings = encode_texts(candidate_texts)
    scored = []
    for track, embedding in zip(tracks, candidate_embeddings):
        score = float(np.dot(query_vector, _normalize(embedding)))
        scored.append((score, track))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [track for _, track in scored]
