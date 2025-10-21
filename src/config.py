import os

BASE_DIR = "/opt/plex-curator"
DATA_DIR = os.path.join(BASE_DIR, "data")
THEMES_DIR = os.path.join(BASE_DIR, "themes")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
CACHE_FILE = os.path.join(DATA_DIR, "tmdb_cache.json")
HISTORY_FILE = os.path.join(DATA_DIR, "playlist_history.json")

# Plex / TMDB / AI configuration
PLEX_URL = os.getenv("PLEX_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
TMDB_KEY = os.getenv("TMDB_KEY")
AI_API_URL = os.getenv("AI_API_URL")
AI_MODEL = "mistral:instruct"

# Curator limits
MAX_TMBD_CANDIDATES = 1000
MAX_AI_SELECTION = 40
MAX_COLLECTION_ITEMS = 15
AI_TIMEOUT = 180
TMDB_PARALLEL_REQUESTS = 10