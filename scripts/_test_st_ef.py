"""Test SentenceTransformerEmbeddingFunction on Jetson."""
import traceback
try:
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    print("Import OK")
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2", device="cpu")
    print(f"Create OK, name={ef.name()}")
    result = ef(["hello world"])
    print(f"Embed OK, dim={len(result[0])}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
