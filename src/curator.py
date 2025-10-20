#!/usr/bin/env python3
import os
import yaml
import json
import config
from core.utils import log, clean_keywords
from core.ai import generate_keywords, suggest_movies
from core.tmdb import search_by_keywords, search_movies_parallel
from core.plex import connect, PlexLibraryCache, find_movies, create_collection

class CurationResult:
    """Stores results from a curation run for display"""
    def __init__(self):
        self.success = False
        self.collection_name = ""
        self.keywords = []
        self.tmdb_first_10 = []
        self.ai_suggestions = []
        self.final_movies = []
        self.ai_match_count = 0
        self.keyword_match_count = 0
        self.errors = []
    
    def to_dict(self):
        return {
            'success': self.success,
            'collection_name': self.collection_name,
            'keywords': self.keywords,
            'tmdb_first_10': self.tmdb_first_10,
            'ai_suggestions': self.ai_suggestions,
            'final_movies': self.final_movies,
            'ai_match_count': self.ai_match_count,
            'keyword_match_count': self.keyword_match_count,
            'total_count': len(self.final_movies),
            'errors': self.errors
        }

def run_curation(theme_file, return_results=False):
    """
    Run a single curation job
    
    Args:
        theme_file: Path to YAML file
        return_results: If True, return CurationResult object instead of bool
    """
    result = CurationResult()
    
    if not os.path.exists(theme_file):
        log(f"[X] Theme file not found: {theme_file}")
        result.errors.append(f"Theme file not found: {theme_file}")
        return result if return_results else False

    curation_name = os.path.basename(theme_file).replace('.yaml', '')
    
    log("=" * 70)
    log(f"RUNNING CURATION: {curation_name}")
    log("=" * 70)

    with open(theme_file, "r") as f:
        theme_cfg = yaml.safe_load(f) or {}

    collection_name = theme_cfg.get("collection_name", curation_name.title())
    result.collection_name = collection_name
    
    month_prompt = theme_cfg.get("prompt", "")
    min_rating = theme_cfg.get("min_rating", config.DEFAULT_MIN_RATING)
    collection_size = theme_cfg.get("collection_size", config.DEFAULT_COLLECTION_SIZE)
    max_ai_selection = collection_size * 3  # 3x collection size

    log(f"[-] Collection Name: {collection_name}")
    log(f"[-] Collection Size: {collection_size}")
    if min_rating > 0:
        log(f"[-] Minimum Rating: {min_rating}/10")

    theme_keywords = theme_cfg.get("keywords", None)
    if not theme_keywords:
        log(f"[-] Generating keywords from collection name...")
        theme_keywords = generate_keywords(collection_name)
    
    if not theme_keywords:
        log("[X] No theme keywords generated")
        result.errors.append("No keywords generated")
        return result if return_results else False

    theme_keywords = clean_keywords(theme_keywords)
    result.keywords = theme_keywords
    log(f"[-] Theme Keywords: {', '.join(theme_keywords)}")
    log("")

    log("STEP 1: Searching TMDB for candidate movies...")
    log("-" * 70)
    tmdb_candidates = search_by_keywords(theme_keywords, max_results=config.MAX_TMBD_CANDIDATES, min_rating=min_rating)
    
    if not tmdb_candidates:
        log("[X] No TMDB candidates found")
        result.errors.append("No TMDB candidates found")
        return result if return_results else False
    
    # Store first 10 for display
    result.tmdb_first_10 = [
        {
            'title': m.get('title'),
            'year': m.get("release_date", "")[:4] if m.get("release_date") else "????",
            'rating': m.get("vote_average", 0)
        }
        for m in tmdb_candidates[:10]
    ]
    log("")

    ai_tmdb_results = []
    
    if month_prompt and month_prompt.strip():
        log("STEP 2: Using AI to suggest movies...")
        log("-" * 70)
        
        suggested_titles = suggest_movies(month_prompt, max_ai_selection)
        result.ai_suggestions = suggested_titles
        
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
    
    matched_movies, ai_count = find_movies(tmdb_candidates, plex_cache, theme_keywords, ai_suggestion_count, collection_size)
    
    result.ai_match_count = ai_count
    result.keyword_match_count = len(matched_movies) - ai_count
    result.final_movies = [m.title for m in matched_movies]
    log("")
    
    if matched_movies:
        log("STEP 4: Creating collection...")
        log("-" * 70)
        create_collection(plex, collection_name, matched_movies, ai_count)
        log("")
        log("=" * 70)
        log("[+] SUCCESS!")
        log("=" * 70)
        result.success = True
        return result if return_results else True
    else:
        log("=" * 70)
        log("[X] FAILED: No Plex matches found")
        log("=" * 70)
        result.errors.append("No Plex matches found")
        return result if return_results else False

def run_all_scheduled():
    """Run all curations that are scheduled"""
    log("=" * 70)
    log("PLEX CURATOR - SCHEDULED RUN")
    log("=" * 70)
    
    schedule = load_cron_schedule()
    
    if not schedule:
        log("[-] No scheduled curations found")
        return
    
    log(f"[-] Found {len(schedule)} scheduled curation(s)")
    log("")
    
    results = []
    for filename, config_data in schedule.items():
        theme_file = os.path.join(config.THEMES_DIR, filename)
        success = run_curation(theme_file)
        results.append((filename, success))
        log("")
    
    log("=" * 70)
    log("SCHEDULED RUN SUMMARY")
    log("=" * 70)
    for filename, success in results:
        status = "[+] SUCCESS" if success else "[X] FAILED"
        log(f"{status}: {filename}")

def run_single_curation(curation_name, return_results=False):
    """Run a specific curation by name"""
    theme_file = os.path.join(config.THEMES_DIR, f"{curation_name}.yaml")
    return run_curation(theme_file, return_results)

def load_cron_schedule():
    if os.path.exists(config.CRON_SCHEDULE_FILE):
        with open(config.CRON_SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    return {}

if __name__ == "__main__":
    import sys
    
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        
        if len(sys.argv) > 1:
            curation_name = sys.argv[1]
            run_single_curation(curation_name)
        else:
            run_all_scheduled()
            
    except KeyboardInterrupt:
        log("\n[X] Interrupted by user")
    except Exception as e:
        log(f"\n[X] Fatal error: {e}")
        import traceback
        traceback.print_exc()