import argparse
import logging
import sys
from typing import Any, Dict

import chromadb
import torch
from transformers import AutoProcessor, ClapModel


CLAP_MODEL_NAME = "laion/clap-htsat-unfused"
COLLECTION_NAME = "street_dance_tracks"
CHROMA_PATH = "./chroma_db"
DEFAULT_TOP_K = 5

logger = logging.getLogger("street-dance-search")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


class ClapTextSearcher:
    def __init__(self, model_name: str = CLAP_MODEL_NAME) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Loading CLAP model '%s' on %s.", model_name, self.device)
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = ClapModel.from_pretrained(model_name).to(self.device)
        self.model.eval()


def create_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(name=COLLECTION_NAME)


def translate_query_to_english(query: str) -> str:
    return query.strip()


def run_search(query_text: str, top_k: int) -> Dict[str, Any]:
    english_query = translate_query_to_english(query_text)
    if english_query != query_text:
        logger.info("Translated query to English: %s", english_query)
    else:
        logger.info("Using English query directly.")

    searcher = ClapTextSearcher()
    collection = create_collection()

    inputs = searcher.processor(text=[english_query], return_tensors="pt", padding=True)
    inputs = {key: value.to(searcher.device) for key, value in inputs.items()}

    with torch.no_grad():
        # Use get_text_features to get the 512D projection
        text_features = searcher.model.get_text_features(**inputs)
        # Flatten and convert to list of floats
        flat_query_embedding = text_features.pooler_output.cpu().numpy().flatten().tolist()

    return collection.query(
        query_embeddings=[flat_query_embedding],
        n_results=top_k,
        include=["metadatas", "distances", "documents"],
    )


def print_results(results: Dict[str, Any]) -> None:
    metadatas = results.get("metadatas", [[]])
    distances = results.get("distances", [[]])

    rows = metadatas[0] if metadatas else []
    scores = distances[0] if distances else []

    if not rows:
        print("No matches found in ChromaDB. Ingest some tracks first.")
        return

    print("Top matches:")
    for index, (metadata, distance) in enumerate(zip(rows, scores), start=1):
        metadata = metadata or {}
        print(f"\n{index}. {metadata.get('track_name', 'Unknown Track')}")
        print(f"   artist: {metadata.get('artist', 'Unknown Artist')}")
        print(f"   bpm: {metadata.get('bpm', 'N/A')}")
        print(f"   energy: {metadata.get('energy', 'N/A')}")
        print(f"   spotify_id: {metadata.get('spotify_id', 'N/A')}")
        print(f"   distance: {distance}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Semantic search over ingested street dance tracks using CLAP text embeddings."
    )
    parser.add_argument(
        "query",
        help="Natural language query in English, for example: 'A heavy drum break beat for breaking'",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of nearest matches to return (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.top_k <= 0:
        parser.error("--top-k must be greater than 0")

    configure_logging(verbose=args.verbose)

    try:
        results = run_search(query_text=args.query, top_k=args.top_k)
        print_results(results)
        return 0
    except Exception as exc:
        logger.exception("Search failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
