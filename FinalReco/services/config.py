from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_PATH = str(BASE_DIR / "chroma_db")
DEFAULT_COLLECTION = "local_music_library"
CLAP_MODEL_NAME = "laion/clap-htsat-unfused"
SPOTIFY_SEARCH_LIMIT = 12
PLAYLIST_SCOPE = "playlist-read-private playlist-read-collaborative"
