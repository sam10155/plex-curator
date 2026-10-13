#!/usr/bin/env python3
import os
import sys
import yaml
import config
from core.utils import log, clean_keywords
from core.ai import generate_keywords, suggest_movies, verify_movies
from core.tmdb import search_by_keywords, search_movies_parallel, discover_movies
from core.plex import connect, PlexLibraryCache, find_movies, create_collection

def run_curation(theme_file):
    """Run a single curation job"""
    if not os.path.exists(theme_file):
        log(f"[X] Theme file not found: {theme_file}")
        return False

    curation_name = os.path.basename(theme_file).replace('.yaml', '')

    log("=" * 70)
    log(f"RUNNING CURATION: {curation_name}")
    log("=" * 70)

    # TMDB API tests
    log("PRE-CHECK: Testing TMDB API connectivity...")
    log("-" * 70)
    from tests.tmdb_test import run_all_tests
    tests_passed = run_all_tests(verbose=False)
    
    if not tests_passed:
        log("[X] TMDB API tests failed - aborting curation")
        log("=" * 70)
        return False
    
    log("[+] TMDB API tests passed")
    log("")

    with open(theme_file, "r") as f:
        theme_cfg = yaml.safe_load(f) or {}

    collection_name = theme_cfg.get("playlist_name", curation_name.title())
    month_prompt = theme_cfg.get("prompt", "")
    min_rating = theme_cfg.get("filters", {}).get("min_rating", 0)
    max_items = theme_cfg.get("max_items", config.DEFAULT_COLLECTION_SIZE)
    promote_to_home = theme_cfg.get("promote_to_home", True)
    library_section = theme_cfg.get("library_section", "Movies")
    requirements = theme_cfg.get("requirements", "")
    tmdb_discover = theme_cfg.get("tmdb_discover")

    log(f"[-] Collection Name: {collection_name}")
    log(f"[-] Target Size: {max_items} items")
    if min_rating > 0:
        log(f"[-] Minimum Rating: {min_rating}/10")

    theme_keywords = theme_cfg.get("keywords", None)
    if not theme_keywords:
        log(f"[-] Generating keywords from collection name...")
        theme_keywords = generate_keywords(collection_name)
    
    if not theme_keywords:
        log("[X] No theme keywords generated")
        return False

    theme_keywords = clean_keywords(theme_keywords)
    log(f"[-] Theme Keywords: {', '.join(theme_keywords)}")
    log("")

    log("STEP 1: Searching TMDB for candidate movies...")
    log("-" * 70)
    if tmdb_discover:
        log(f"[-] Using TMDB Discover filters: {tmdb_discover}")
        tmdb_candidates = discover_movies(tmdb_discover, max_results=config.MAX_TMDB_CANDIDATES, min_rating=min_rating)
        if not tmdb_candidates:
            log("[-] Discover returned nothing — falling back to keyword search")
            tmdb_candidates = search_by_keywords(theme_keywords, max_results=config.MAX_TMDB_CANDIDATES, min_rating=min_rating)
    else:
        tmdb_candidates = search_by_keywords(theme_keywords, max_results=config.MAX_TMDB_CANDIDATES, min_rating=min_rating)

    if not tmdb_candidates:
        log("[X] No TMDB candidates found")
        return False
    log("")

    ai_tmdb_results = []
    
    if month_prompt and month_prompt.strip():
        log("STEP 2: Using AI to suggest movies...")
        log("-" * 70)
        
        suggested_titles = suggest_movies(month_prompt, config.MAX_AI_SELECTION, requirements)
        
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
    plex_cache = PlexLibraryCache(plex, library_section)
    ai_suggestion_count = len(ai_tmdb_results)
    
    matched_movies, ai_count = find_movies(tmdb_candidates, plex_cache, theme_keywords, ai_suggestion_count, max_items)
    log("")

    if requirements.strip() and matched_movies:
        log("STEP 3b: Verifying matches against hard requirements...")
        log("-" * 70)
        keep_idx = verify_movies(requirements, matched_movies)
        ai_count = sum(1 for i in keep_idx if i < ai_count)
        matched_movies = [matched_movies[i] for i in keep_idx]
        log(f"[-] {len(matched_movies)} movies passed verification")
        log("")

    if matched_movies:
        log("STEP 4: Creating collection...")
        log("-" * 70)
        create_collection(plex, collection_name, matched_movies, ai_count,
                          promote_to_home, library_section)
        log("")
        log("=" * 70)
        log("[+] SUCCESS!")
        log("=" * 70)
        return True
    else:
        log("=" * 70)
        log("[X] FAILED: No Plex matches found")
        log("=" * 70)
        return False

def run_single_curation(curation_name):
    """Run a specific curation by name (for web UI)"""
    theme_file = os.path.join(config.THEMES_DIR, f"{curation_name}.yaml")
    return run_curation(theme_file)

if __name__ == "__main__":
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)

        if len(sys.argv) > 1:
            # Run specific curation: python curator.py october
            success = run_single_curation(sys.argv[1])
            sys.exit(0 if success else 1)
        else:
            print("Usage: python3 src/curator.py <curation_name>")
            sys.exit(1)

    except KeyboardInterrupt:
        log("\n[X] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"\n[X] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)