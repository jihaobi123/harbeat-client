from typing import List

from services.clap_service import encode_texts
from services.library_service import create_collection


def search_collection(query_text: str, collection_name: str, top_k: int = 10) -> List[dict]:
    collection = create_collection(collection_name)
    query_embedding = encode_texts([query_text])[0].flatten().tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["metadatas", "distances", "documents"],
    )

    metadatas = results.get("metadatas", [[]])
    distances = results.get("distances", [[]])
    documents = results.get("documents", [[]])
    rows = []

    for metadata, distance, document in zip(
        metadatas[0] if metadatas else [],
        distances[0] if distances else [],
        documents[0] if documents else [],
    ):
        item = dict(metadata or {})
        item["distance"] = float(distance)
        item["document"] = document
        rows.append(item)

    rows.sort(key=lambda item: item.get("distance", 0.0))
    return rows
