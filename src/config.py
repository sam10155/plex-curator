import os

BASE_DIR = "/opt/plex-curator"
DATA_DIR = os.path.join(BASE_DIR, "data")
THEMES_DIR = os.path.join(BASE_DIR, "themes")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
CACHE_FILE = os.path.join(DATA_DIR, "tmdb_cache.json")
HISTORY_FILE = os.path.join(DATA_DIR, "playlist_history.json")
LOG_DIR = os.path.join(DATA_DIR, "logs")

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Plex / TMDB / AI configuration
PLEX_URL = os.getenv("PLEX_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
TMDB_KEY = os.getenv("TMDB_KEY")
AI_API_URL = os.getenv("AI_API_URL")
AI_MODEL = "mistral:instruct"

# Curator limits
MAX_TMDB_CANDIDATES = 200 
MAX_AI_SELECTION = 40  
DEFAULT_COLLECTION_SIZE = 100  
AI_TIMEOUT = 180 
TMDB_PARALLEL_REQUESTS = 10  