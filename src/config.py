import os

BASE_DIR = os.getenv("CURATOR_BASE_DIR", "/opt/plex-curator")
DATA_DIR = os.path.join(BASE_DIR, "data")
THEMES_DIR = os.path.join(BASE_DIR, "themes")
CHANNELS_DIR = os.path.join(BASE_DIR, "channels")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
LOG_DIR = os.path.join(DATA_DIR, "logs")

SCHEDULES_FILE = os.path.join(DATA_DIR, "schedules.json")
JOB_STATUS_FILE = os.path.join(DATA_DIR, "job_status.json")
CHANNEL_HISTORY_FILE = os.path.join(DATA_DIR, "channel_history.json")
TMDB_TV_CACHE_FILE = os.path.join(DATA_DIR, "tmdb_tv_cache.json")
LEGACY_CRON_SCHEDULE_FILE = os.path.join(DATA_DIR, "cron_schedule.json")

# Ensure log directory exists (may fail outside the container; that's fine)
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except OSError:
    pass

# Plex / TMDB / AI configuration
PLEX_URL = os.getenv("PLEX_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
TMDB_KEY = os.getenv("TMDB_KEY")
AI_API_URL = os.getenv("AI_API_URL")
AI_MODEL = os.getenv("AI_MODEL", "qwen3:8b")

# Web UI
WEB_PORT = int(os.getenv("WEB_PORT", "8088"))
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")

# Curator limits
MAX_TMDB_CANDIDATES = 200
MAX_AI_SELECTION = 40
DEFAULT_COLLECTION_SIZE = 100
AI_TIMEOUT = 180
TMDB_PARALLEL_REQUESTS = 10

# TV channel defaults
DEFAULT_TARGET_HOURS = 4
DEFAULT_MAX_HOURS = 6
DEFAULT_SHOWS_PER_BLOCK = 6
MAX_SHOW_CANDIDATES = 150
MAX_EPISODE_CANDIDATES = 250
RECENT_EPISODE_MEMORY = 300

# In-app scheduler
SCHEDULER_TICK_SECONDS = 30
