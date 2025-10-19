#!/usr/bin/env python3
import os
import yaml
import datetime
import config
from core.utils import log, clean_keywords
from core.ai import generate_keywords, suggest_movies
from core.tmdb import search_by_keywords, search_movies_parallel
from core.plex import connect, PlexLibraryCache, find_movies, create_collection

def run_curator():
    log("=" * 70)
    log("PLEX CURATOR STARTED")
    log("=" * 70)

    month_name = datetime.datetime.now().strftime("%B").lower()
    theme_file = os.path.join(config.THEMES_DIR, f"{month_name}.yaml")
    
    if not os.path.exists(theme_file):
        log(f"[X] No theme file found for {month_name}")
        log(f"    Expected: {theme_file}")
        return

    with open(theme_file, "r") as f:
        theme_cfg = yaml.safe_load(f)

    collection_name = theme_cfg.get("playlist_name", f"{month_name.title()} Picks")
    month_prompt = theme_cfg.get("prompt", "")
    min_rating = theme_cfg.get("filters", {}).get("min_rating", 0)

    log(f"[-] Collection Name: {collection_name}")
    log(f"[-] Month: {month_name.title()}")
    if min_rating > 0:
        log(f"[-] Minimum Rating: {min_rating}/10")

    theme_keywords = theme_cfg.get("keywords", None)
    if not theme_keywords:
        log(f"[-] Generating keywords from collection name...")
        theme_keywords = generate_keywords(collection_name)
    
    if not theme_keywords:
        log("[X] No theme keywords generated")
        return

    theme_keywords = clean_keywords(theme_keywords)
    log(f"[-] Theme Keywords: {', '.join(theme_keywords)}")
    log("")

    log("STEP 1: Searching TMDB for candidate movies...")
    log("-" * 70)
    tmdb_candidates = search_by_keywords(theme_keywords, max_results=config.MAX_TMBD_CANDIDATES, min_rating=min_rating)
    
    if not tmdb_candidates:
        log("[X] No TMDB candidates found")
        return
    log("")

    ai_tmdb_results = []
    
    if month_prompt and month_prompt.strip():
        log("STEP 2: Using AI to suggest movies...")
        log("-" * 70)
        
        suggested_titles = suggest_movies(month_prompt, config.MAX_AI_SELECTION)
        
        if suggested_titles:
            log(f"[-] AI suggested {len(suggested_titles)} titles")
            log("")
            log("STEP 2b: Searching TMDB (parallel)...")
            log("-" * 70)
            
            ai_tmdb_results, seen_ids = search_movies_parallel(suggested_titles, min_rating)
            
            if ai_tmdb_results:
                log(f"")
                log(f"[-] Found {len(ai_tmdb_results)} AI-suggested movies on TMDB")
                log(f"[-] Keeping {len(tmdb_candidates)} keyword results as backup")
                
                combined_candidates = ai_tmdb_results + [
                    m for m in tmdb_candidates 
                    if m.get("id") not in seen_ids
                ]
                tmdb_candidates = combined_candidates
                log(f"[-] Total candidate pool: {len(tmdb_candidates)} movies")
            else:
                log("[X] No AI-suggested movies found on TMDB")
        log("")
    else:
        log("STEP 2: Skipping AI curation (no prompt)")
        log("-" * 70)
        log("")

    log("STEP 3: Matching to Plex library...")
    log("-" * 70)
    
    plex = connect()
    plex_cache = PlexLibraryCache(plex)
    ai_suggestion_count = len(ai_tmdb_results)
    
    matched_movies, ai_count = find_movies(tmdb_candidates, plex_cache, theme_keywords, ai_suggestion_count)
    log("")
    
    if matched_movies:
        log("STEP 4: Creating collection...")
        log("-" * 70)
        create_collection(plex, collection_name, matched_movies, ai_count)
        log("")
        log("=" * 70)
        log("[+] SUCCESS!")
        log("=" * 70)
    else:
        log("=" * 70)
        log("[X] FAILED: No Plex matches found")
        log("=" * 70)

if __name__ == "__main__":
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        run_curator()
    except KeyboardInterrupt:
        log("\n[X] Interrupted by user")
    except Exception as e:
        log(f"\n[X] Fatal error: {e}")
        import traceback
        traceback.print_exc()