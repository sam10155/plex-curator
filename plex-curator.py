#!/usr/bin/env python3
import os
import json
import yaml
import datetime
import unicodedata
import requests
from difflib import SequenceMatcher
from plexapi.server import PlexServer
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
MAX_COLLECTION_ITEMS = 15

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
    seen_ids = set()
    
    for kw in keywords:
        search = tmdb.Search()
        try:
            resp = search.movie(query=kw)
            for r in resp.get("results", []):
                movie_id = r.get("id")
                if movie_id in seen_ids:
                    continue
                seen_ids.add(movie_id)
                
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
    
    log(f"TMDB found {len(results)} unique movies")
    
    # Show first 10 results
    if results:
        log("First 10 TMDB results:")
        for i, movie in enumerate(results[:10], 1):
            year = movie.get("release_date", "")[:4] if movie.get("release_date") else "????"
            rating = movie.get("vote_average", 0)
            log(f"  {i}. {movie.get('title')} ({year}) - Rating: {rating}/10")
    
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
        log(f"[DEBUG] Raw AI response (first 200 chars): {response_text[:200]}...")
        log(f"[DEBUG] Cleaned AI list ({len(cleaned_list)} items): {cleaned_list[:5]}...")
        return cleaned_list
    except Exception as e:
        log(f"[ERROR] AI request failed: {e}")
        return []


def generate_keywords_from_name(collection_name):
    """
    Generate a theme-agnostic list of keywords from the collection name.
    """
    prompt = f"Generate 7 concise keywords describing the theme/genre of a movie collection named: '{collection_name}'. Return strictly as a JSON list of words."
    keywords = ai_request(prompt)
    if not keywords:
        keywords = list(set(re.findall(r'\w+', collection_name.lower())))
    return keywords


# -------------------------
# Title Normalization
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


# -------------------------
# Plex Matching
# -------------------------
def find_movies_on_plex(tmdb_movies, plex, keywords, ai_count_hint=0):
    """
    Match TMDB movies to Plex library, with ranked keyword fallback.
    Returns actual Plex movie objects ready for playlist creation.
    Also returns stats about AI vs keyword matches.
    
    ai_count_hint: number of AI-suggested movies at the start of tmdb_movies list
    """
    plex_movies = plex.library.section("Movies").all()
    matched = []
    ai_matched_count = 0  # Track how many came from AI selection

    plex_map = {normalize_title(m.title): m for m in plex_movies}
    log(f"[DEBUG] Searching Plex library ({len(plex_movies)} movies) with {len(tmdb_movies)} TMDB candidates")

    # First pass: exact title matches from TMDB candidates
    # Track which ones came from AI suggestions (first N items in the list)
    for idx, tmdb_movie in enumerate(tmdb_movies):
        tmdb_title = normalize_title(tmdb_movie.get("title", ""))
        if tmdb_title in plex_map:
            plex_movie = plex_map[tmdb_title]
            if plex_movie not in matched:
                matched.append(plex_movie)
                if idx < ai_count_hint:
                    ai_matched_count += 1
                    log(f"[DEBUG] AI Match: {plex_movie.title}")
                else:
                    log(f"[DEBUG] Keyword Match: {plex_movie.title}")
        if len(matched) >= MAX_COLLECTION_ITEMS:
            break

    # Second pass: keyword-based fallback if needed
    if len(matched) < MAX_COLLECTION_ITEMS:
        log(f"[DEBUG] Found {ai_matched_count} AI matches and {len(matched) - ai_matched_count} keyword matches")
        log(f"[DEBUG] Need {MAX_COLLECTION_ITEMS - len(matched)} more movies, using ranked keyword fallback...")
        scored = []

        for movie in plex_movies:
            if movie in matched:
                continue
                
            searchable = " ".join([
                movie.title or "",
                getattr(movie, "summary", "") or "",
                " ".join([g.tag for g in getattr(movie, "genres", [])])
            ]).lower()

            # Count keyword hits
            hit_count = sum(1 for kw in keywords if kw.lower() in searchable)
            if hit_count == 0:
                continue

            # Compute fuzzy title similarity to keywords
            fuzz_score = max(
                SequenceMatcher(None, normalize_title(movie.title), normalize_title(kw)).ratio()
                for kw in keywords
            )

            total_score = (hit_count * 20) + (fuzz_score * 100)
            if total_score >= 70:  # Require at least one solid thematic hit
                scored.append((total_score, movie))

        # Sort high-to-low and pick top results
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, movie in scored:
            if movie not in matched:
                matched.append(movie)
                log(f"[DEBUG] Keyword Match (score: {score:.1f}): {movie.title}")
            if len(matched) >= MAX_COLLECTION_ITEMS:
                break

    matched = [m for m in matched if hasattr(m, "ratingKey")]
    log(f"Final collection: {ai_matched_count}/{len(matched)} movies from AI selection, {len(matched) - ai_matched_count} from keyword fallback")
    log(f"Movies: {[m.title for m in matched]}")
    
    return matched[:MAX_COLLECTION_ITEMS], ai_matched_count


# -------------------------
# Collection Creation
# -------------------------
def create_or_replace_collection(plex, name, items, ai_count):
    # Validate items
    items = [i for i in items if hasattr(i, "ratingKey") and getattr(i, "ratingKey")]
    if not items:
        log(f"[X] No valid Plex items to add for collection '{name}', skipping creation")
        return
    
    log(f"[-] Creating collection with {len(items)} items ({ai_count} from AI, {len(items) - ai_count} from keywords)")

    # Get the Movies library section
    try:
        movies_section = plex.library.section("Movies")
    except Exception as e:
        log(f"[X] Failed to get Movies library: {e}")
        raise

    # Check if collection already exists and delete it
    try:
        existing_collections = movies_section.collections()
        for collection in existing_collections:
            if collection.title == name:
                log(f"[-] Deleting existing collection: {name}")
                collection.delete()
                break
    except Exception as e:
        log(f"[X] Error checking existing collections: {e}")

    # Create new collection
    try:
        # Create collection by editing the first item
        first_item = items[0]
        first_item.addCollection(name)
        
        # Add remaining items to the collection
        for item in items[1:]:
            item.addCollection(name)
        
        # Get the newly created collection to configure it
        movies_section.reload()
        collection = None
        for coll in movies_section.collections():
            if coll.title == name:
                collection = coll
                break
        
        if collection:
            try:
                collection.editSortTitle(f"!{name}")
                
                visibility_hub = collection.visibility()
                visibility_hub.promoteHome()
                visibility_hub.promoteShared()
                
                log(f"[+] Collection '{name}' created successfully!")
                log(f"    - Total movies: {len(items)}")
                log(f"    - AI-curated: {ai_count}")
                log(f"    - Keyword-matched: {len(items) - ai_count}")
                log(f"    - Sort title: !{name}")
                log(f"    - Promoted to home screen")
            except Exception as e:
                log(f"[+] Collection '{name}' created successfully!")
                log(f"    - Total movies: {len(items)}")
                log(f"    - AI-curated: {ai_count}")
                log(f"    - Keyword-matched: {len(items) - ai_count}")
                log(f"[-] Could not set all preferences: {e}")
                log(f"[-] Manually promote to home in Plex if desired")
            
            return collection
        else:
            log(f"[X] Collection created but couldn't retrieve it for configuration")
            
    except Exception as e:
        log(f"[X] Failed to create collection: {e}")
        raise


# -------------------------
# Main Curator Logic
# -------------------------
def run_curator():
    log("=" * 70)
    log("PLEX CURATOR STARTED")
    log("=" * 70)

    month_name = datetime.datetime.now().strftime("%B").lower()
    theme_file = os.path.join(BASE_DIR, "themes", f"{month_name}.yaml")
    
    if not os.path.exists(theme_file):
        log(f"[X] No theme file found for {month_name}")
        log(f"    Expected: {theme_file}")
        return

    with open(theme_file, "r") as f:
        theme_cfg = yaml.safe_load(f)

    # Get collection name from YAML (field is still called "playlist_name" for compatibility)
    collection_name = theme_cfg.get("playlist_name", f"{month_name.title()} Picks")
    month_prompt = theme_cfg.get("prompt", "")
    min_rating = theme_cfg.get("filters", {}).get("min_rating", 0)

    log(f"[-] Collection Name: {collection_name}")
    log(f"[-] Month: {month_name.title()}")
    if min_rating > 0:
        log(f"[-] Minimum Rating: {min_rating}/10")

    # Get or generate keywords
    theme_keywords = theme_cfg.get("keywords", None)
    if not theme_keywords:
        log(f"[-] No keywords in YAML, generating from collection name...")
        theme_keywords = generate_keywords_from_name(collection_name)
    
    if not theme_keywords:
        log("[X] No theme keywords generated, skipping collection creation")
        return

    theme_keywords = clean_keywords(theme_keywords)
    log(f"[-] Theme Keywords: {', '.join(theme_keywords)}")
    log("")

    # TMDB Search
    log("STEP 1: Searching TMDB for candidate movies...")
    log("-" * 70)
    tmdb_candidates = tmdb_search_by_keywords(theme_keywords, max_results=MAX_TMBD_CANDIDATES, min_rating=min_rating)
    
    if not tmdb_candidates:
        log("[X] No TMDB candidates found")
        return
    log("")

    # AI selection - let AI suggest movies, then search TMDB for them
    ai_tmdb_results = []  # Initialize outside the if block
    
    if month_prompt and month_prompt.strip():
        log("STEP 2: Using AI to suggest movies for the theme...")
        log("-" * 70)
        
        # Ask AI to suggest movies directly (not from TMDB list)
        ai_selection_prompt = f"{month_prompt}\n\nSuggest up to {MAX_AI_SELECTION} well-known movie titles that best fit this theme. Return ONLY a JSON list of movie titles (no years, no descriptions, no explanations)."
        suggested_titles = ai_request(ai_selection_prompt)
        
        # Clean AI response
        cleaned_titles = []
        for title in suggested_titles:
            title = re.sub(r'\s*[-:(].*$', '', title)  # Remove years, descriptions
            title = title.strip('"\'')
            if title and len(title) > 2 and not title.startswith(("It seems", "Here", "From", "Sure", "I'd", "Based")):
                cleaned_titles.append(title)
        
        if cleaned_titles:
            log(f"AI suggested {len(cleaned_titles)} titles: {cleaned_titles[:10]}")
            log("")
            log("STEP 2b: Searching TMDB for AI-suggested movies...")
            log("-" * 70)
            
            # Search TMDB for each AI-suggested title
            seen_ids = set()
            
            for title in cleaned_titles:
                try:
                    search = tmdb.Search()
                    resp = search.movie(query=title)
                    results = resp.get("results", [])
                    
                    if results:
                        # Take the first (most relevant) result
                        movie = results[0]
                        movie_id = movie.get("id")
                        
                        if movie_id not in seen_ids:
                            rating = movie.get("vote_average") or 0
                            if rating >= min_rating:
                                ai_tmdb_results.append(movie)
                                seen_ids.add(movie_id)
                                year = movie.get("release_date", "")[:4] if movie.get("release_date") else "????"
                                log(f"  [+] Found: {movie.get('title')} ({year}) - Rating: {rating}/10")
                            else:
                                log(f"  [X] Skipped: {movie.get('title')} (rating {rating} < {min_rating})")
                    else:
                        log(f"  [X] Not found on TMDB: {title}")
                except Exception as e:
                    log(f"  [X] Error searching for '{title}': {e}")
            
            if ai_tmdb_results:
                # Combine with keyword results (keyword results as backup)
                log(f"\n[-] Found {len(ai_tmdb_results)} AI-suggested movies on TMDB")
                log(f"[-] Also keeping {len(tmdb_candidates)} keyword-based results as backup")
                
                # Prioritize AI results by putting them first
                combined_candidates = ai_tmdb_results + [
                    m for m in tmdb_candidates 
                    if m.get("id") not in seen_ids
                ]
                tmdb_candidates = combined_candidates
                log(f"[-] Total candidate pool: {len(tmdb_candidates)} movies")
            else:
                log("[X] No AI-suggested movies found on TMDB, using keyword results only")
        log("")
    else:
        log("STEP 2: Skipping AI curation (no prompt provided)")
        log("-" * 70)
        log("")

    # Plex Matching
    log("STEP 3: Matching to Plex library...")
    log("-" * 70)
    movies_library = plex.library.section("Movies")
    
    # Pass count of AI suggestions to help with tracking
    ai_suggestion_count = len(ai_tmdb_results)
    
    matched_movies, ai_count = find_movies_on_plex(tmdb_candidates, plex, theme_keywords, ai_suggestion_count)
    log("")
    
    if matched_movies:
        log("STEP 4: Creating collection...")
        log("-" * 70)
        create_or_replace_collection(plex, collection_name, matched_movies, ai_count)
        log("")
        log("=" * 70)
        log("[+] SUCCESS!")
        log("=" * 70)
    else:
        log("=" * 70)
        log("[X] FAILED: No Plex matches found")
        log("=" * 70)
        log("[-] Suggestions:")
        log("    - Try broader keywords")
        log("    - Check if these movies exist in your library")
        log("    - Lower the minimum rating filter")


# -------------------------
# Main Entry Point
# -------------------------
if __name__ == "__main__":
    try:
        run_curator()
    except KeyboardInterrupt:
        log("\n[X] Interrupted by user")
    except Exception as e:
        log(f"\n[X] Fatal error: {e}")
        import traceback
        traceback.print_exc()