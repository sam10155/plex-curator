#!/usr/bin/env python3
import os
import json
import yaml
import datetime
import time
import unicodedata
import random
import requests
import schedule
from difflib import SequenceMatcher
from plexapi.server import PlexServer
from plexapi.playlist import Playlist
import tmdbsimple as tmdb
import re

# -------------------------
# Paths & Config
# -------------------------
BASE_DIR = "/opt/plex-curator"
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "tmdb_cache.json")
HISTORY_FILE = os.path.join(DATA_DIR, "playlist_history.json")

PLEX_URL = os.getenv("PLEX_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
TMDB_KEY = os.getenv("TMDB_KEY")
AI_API_URL = os.getenv("AI_API_URL")

MAX_TMBD_CANDIDATES = 1000
MAX_AI_SELECTION = 50
MAX_PLAYLIST_ITEMS = 15

# -------------------------
# Utilities
# -------------------------
def log(msg):
    print(f"{datetime.datetime.now().isoformat()} - {msg}", flush=True)

def load_json_file(file_path):
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        log(f"[WARN] JSON decode error in {file_path}, resetting file")
        return {}

def save_json_file(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

# -------------------------
# Setup
# -------------------------
os.makedirs(DATA_DIR, exist_ok=True)
plex = PlexServer(PLEX_URL, PLEX_TOKEN)
tmdb.API_KEY = TMDB_KEY
tmdb_cache = load_json_file(CACHE_FILE)
history = load_json_file(HISTORY_FILE)

# -------------------------
# TMDB Search
# -------------------------
def tmdb_search_by_keywords(keywords, max_results=MAX_TMBD_CANDIDATES, min_rating=0):
    results = []
    for kw in keywords:
        search = tmdb.Search()
        try:
            resp = search.movie(query=kw)
            for r in resp.get("results", []):
                if r in results:
                    continue
                rating = r.get("vote_average") or 0
                if rating < min_rating:
                    continue
                results.append(r)
                if len(results) >= max_results:
                    break
        except Exception as e:
            log(f"[WARN] TMDB search error for '{kw}': {e}")
        if len(results) >= max_results:
            break
    log(f"TMDB found {len(results)} movies matching keywords: {keywords}")
    return results

# -------------------------
# Keyword Cleaning
# -------------------------
def clean_keywords(keywords):
    return [re.sub(r'^\d+\.\s*', '', kw).strip() for kw in keywords if kw.strip()]

# -------------------------
# AI Helpers
#--------------------------
def parse_ollama_response(resp_text):
    """
    Parse AI output into a clean Python list of strings.
    Handles:
    - Proper JSON lists
    - Comma-separated strings
    - Line-separated strings with bullets/numbers
    """
    resp_text = resp_text.strip()
    if not resp_text:
        return []

    # Attempt strict JSON parsing first
    try:
        parsed = json.loads(resp_text)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except json.JSONDecodeError:
        pass

    # Remove enclosing { [ ] } if present
    resp_text = resp_text.strip("{}[]\n ")
    
    # Split by line or commas
    candidates = []
    if "\n" in resp_text:
        for line in resp_text.splitlines():
            line = line.strip("-• \t\"")
            if line:
                candidates.append(line)
    elif "," in resp_text:
        for part in resp_text.split(","):
            part = part.strip("\" ")
            if part:
                candidates.append(part)
    else:
        candidates.append(resp_text)

    # Deduplicate and clean
    cleaned = []
    for c in candidates:
        c = re.sub(r'^\d+\.\s*', '', c)  # remove numbering like "1. "
        c = c.strip()
        if c and c not in cleaned:
            cleaned.append(c)
    return cleaned


def ai_request(prompt):
    """
    Calls the AI endpoint and returns a clean list of titles/keywords.
    """
    try:
        resp = requests.post(AI_API_URL, json={"model": "mistral:instruct", "prompt": prompt}, stream=True, timeout=180)
        response_text = ""
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                try:
                    data = json.loads(line)
                    if "response" in data:
                        response_text += data["response"]
                except json.JSONDecodeError:
                    response_text += line
        cleaned_list = parse_ollama_response(response_text)
        log(f"[DEBUG] Raw AI response: {response_text}")
        log(f"[DEBUG] Cleaned AI list: {cleaned_list}")
        return cleaned_list
    except Exception as e:
        log(f"[ERROR] AI request failed: {e}")
        return []


def generate_keywords_from_name(playlist_name):
    """
    Generate a theme-agnostic list of keywords from the playlist name.
    Falls back to splitting the name if AI fails.
    """
    prompt = f"Generate 7 concise keywords describing the theme/genre of a movie playlist named: '{playlist_name}'. Return strictly as a JSON list of words."
    keywords = ai_request(prompt)
    if not keywords:
        # fallback: split by space and remove duplicates
        keywords = list(set(re.findall(r'\w+', playlist_name.lower())))
    return keywords


# -------------------------
# Plex Matching
# -------------------------
def normalize_title(title):
    """
    Normalize titles for comparison:
    - Lowercase
    - Remove parentheses content (years)
    - Remove punctuation
    - Strip whitespace
    """
    title = title.lower()
    title = re.sub(r"\(.*?\)", "", title)  # remove anything in parentheses
    title = re.sub(r"[^\w\s]", "", title)  # remove punctuation
    title = unicodedata.normalize("NFKD", title)  # normalize unicode
    return title.strip()

from difflib import SequenceMatcher

def find_movies_on_plex(tmdb_movies, plex, keywords):
    """
    Match TMDB movies to Plex library, with ranked keyword fallback.
    Returns actual Plex movie objects ready for playlist creation.
    """
    plex_movies = plex.library.section("Movies").all()
    matched = []

    plex_map = {normalize_title(m.title): m for m in plex_movies}
    log(f"[DEBUG] Searching Plex library with {len(tmdb_movies)} TMDB candidates")

    for tmdb_movie in tmdb_movies:
        tmdb_title = normalize_title(tmdb_movie.get("title", ""))
        if tmdb_title in plex_map:
            plex_movie = plex_map[tmdb_title]
            if plex_movie not in matched:
                matched.append(plex_movie)
                log(f"[DEBUG] Matched: {plex_movie.title}")
        if len(matched) >= MAX_PLAYLIST_ITEMS:
            break

    if len(matched) < MAX_PLAYLIST_ITEMS:
        log(f"[DEBUG] Only found {len(matched)} direct matches, using ranked keyword fallback...")
        scored = []

        for movie in plex_movies:
            searchable = " ".join([
                movie.title or "",
                getattr(movie, "summary", "") or "",
                " ".join([g.tag for g in getattr(movie, "genres", [])])
            ]).lower()

            # Count keyword hits
            hit_count = sum(1 for kw in keywords if kw.lower() in searchable)
            if hit_count == 0:
                continue

            # Compute fuzzy title similarity
            fuzz_score = max(
                SequenceMatcher(None, normalize_title(movie.title), normalize_title(kw)).ratio()
                for kw in keywords
            )

            total_score = (hit_count * 20) + (fuzz_score * 100)
            if total_score >= 70:  # Require at least one solid thematic hit
                scored.append((total_score, movie))

        # Sort high-to-low and pick top results
        scored.sort(key=lambda x: x[0], reverse=True)
        for _, movie in scored:
            if movie not in matched:
                matched.append(movie)
                log(f"[DEBUG] Ranked keyword match: {movie.title}")
            if len(matched) >= MAX_PLAYLIST_ITEMS:
                break

    matched = [m for m in matched if hasattr(m, "ratingKey")]
    log(f"Final playlist items ({len(matched)}): {[m.title for m in matched]}")
    return matched[:MAX_PLAYLIST_ITEMS]



# -------------------------
# Playlist Creation
# -------------------------
def create_or_replace_playlist(name, items):
    # Validate items
    items = [i for i in items if hasattr(i, "ratingKey") and getattr(i, "ratingKey")]
    if not items:
        log(f"[WARN] No valid Plex items to add for playlist '{name}', skipping creation")
        return
    
    log(f"[DEBUG] Creating playlist with {len(items)} items")
    log(f"[DEBUG] Item types: {[type(i).__name__ for i in items[:3]]}")
    log(f"[DEBUG] Item ratingKeys: {[i.ratingKey for i in items[:3]]}")

    # Delete old playlist if exists
    for pl in plex.playlists():
        if pl.title == name:
            log(f"Deleting old playlist: {name}")
            pl.delete()
            break

    # Create new playlist - explicitly pass items parameter
    try:
        playlist = Playlist.create(plex, name, items=items)
        log(f"Playlist created: {name} ({len(items)} items)")
    except Exception as e:
        log(f"[ERROR] Failed to create playlist: {e}")
        log(f"[DEBUG] Attempting alternative creation method...")
        try:
            # Alternative: use server.createPlaylist method
            playlist = plex.createPlaylist(title=name, items=items)
            log(f"Playlist created via alternative method: {name} ({len(items)} items)")
        except Exception as e2:
            log(f"[ERROR] Alternative method also failed: {e2}")
            raise


# -------------------------
# Main Curator Logic
# -------------------------
def run_curator():
    log("Curator Started...")

    month_name = datetime.datetime.now().strftime("%B").lower()
    theme_file = os.path.join(BASE_DIR, "themes", f"{month_name}.yaml")
    if not os.path.exists(theme_file):
        log(f"No theme file for {month_name}, skipping.")
        return

    with open(theme_file, "r") as f:
        theme_cfg = yaml.safe_load(f)

    playlist_name = theme_cfg.get("playlist_name", f"{month_name.title()} Picks")
    month_prompt = theme_cfg.get("prompt", "")
    min_rating = theme_cfg.get("filters", {}).get("min_rating", 0)

    theme_keywords = theme_cfg.get("keywords", None)
    if not theme_keywords:
        log(f"[INFO] No keywords in YAML, generating from playlist name '{playlist_name}'...")
        theme_keywords = generate_keywords_from_name(playlist_name)
    if not theme_keywords:
        log("[WARN] No theme keywords generated, skipping playlist creation")
        return

    theme_keywords = clean_keywords(theme_keywords)
    log(f"Using keywords: {theme_keywords}")

    # TMDB Search - this gets us candidates based on keywords
    tmdb_candidates = tmdb_search_by_keywords(theme_keywords, max_results=MAX_TMBD_CANDIDATES, min_rating=min_rating)
    
    if not tmdb_candidates:
        log("[WARN] No TMDB candidates found, skipping playlist creation")
        return

    # AI selection - let AI pick the best titles from our candidates
    candidate_text = "\n".join([f"{m['title']}" for m in tmdb_candidates[:100]])  # Limit for token size
    ai_selection_prompt = f"{month_prompt}\n\nFrom this list of movie titles, select up to {MAX_AI_SELECTION} that best fit the theme. Return ONLY the exact movie titles as a JSON list with no descriptions or extra text:\n{candidate_text}"
    selected_titles = ai_request(ai_selection_prompt)
    
    # Extract just the title if AI added descriptions (split on " - " or " : ")
    cleaned_selected_titles = []
    for title in selected_titles:
        # Remove common AI-added prefixes/suffixes
        title = re.sub(r'\s*[-:]\s*.*$', '', title)  # Remove everything after " - " or " : "
        title = title.strip('"\'')
        if title and not title.startswith("It seems") and not title.startswith("Here"):
            cleaned_selected_titles.append(title)
    
    log(f"[DEBUG] AI selected {len(cleaned_selected_titles)} titles: {cleaned_selected_titles[:10]}")

    # Filter TMDB candidates to only AI-selected ones (using normalized matching)
    if cleaned_selected_titles:
        normalized_selected = {normalize_title(t) for t in cleaned_selected_titles}
        filtered_candidates = [
            m for m in tmdb_candidates 
            if normalize_title(m.get("title", "")) in normalized_selected
        ]
        if filtered_candidates:
            tmdb_candidates = filtered_candidates
            log(f"[DEBUG] Filtered to {len(tmdb_candidates)} AI-selected candidates")
        else:
            log("[DEBUG] No matches after AI filtering, using all TMDB candidates")

    # Plex Matching - find these movies in the user's Plex library
    matched_movies = find_movies_on_plex(tmdb_candidates, plex, theme_keywords)
    
    if matched_movies:
        create_or_replace_playlist(playlist_name, matched_movies)
    else:
        log(f"[WARN] No Plex matches found, skipping playlist '{playlist_name}'")

# -------------------------
# Scheduler
# -------------------------
def run_monthly():
    if datetime.datetime.now().day == 1:
        run_curator()

def main():
    run_curator()
    schedule.every().day.at("00:30").do(run_monthly)
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
