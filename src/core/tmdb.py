#!/usr/bin/env python3
from tmdbv3api import TMDb, Movie
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.utils import log
import config

# -------------------------
# TMDb Initialization
# -------------------------
tmdb = TMDb()
tmdb.api_key = config.TMDB_KEY
tmdb.language = "en"
tmdb.debug = False # For verbosity, TODO: make flag set at runtime

movie_client = Movie()


# ---------------------------------------------------------
# Search by keywords — returns merged unique movie results
# ---------------------------------------------------------
def search_by_keywords(keywords, max_results=1000, min_rating=0):
    results = []
    seen_ids = set()

    for kw in keywords:
        try:
            resp = movie_client.search(kw)
        except Exception as e:
            log(f"[X] TMDB search error for '{kw}': {e}")
            continue

        if not resp:
            continue

        for r in resp:
            movie_id = getattr(r, "id", None)
            if movie_id is None or movie_id in seen_ids:
                continue

            rating = getattr(r, "vote_average", 0) or 0
            if rating < min_rating:
                continue

            movie_dict = r.__dict__

            results.append(movie_dict)
            seen_ids.add(movie_id)

            if len(results) >= max_results:
                break

        if len(results) >= max_results:
            break

    log(f"[-] TMDB found {len(results)} unique movies")

    if results:
        log("[-] First 10 TMDB results:")
        for i, movie in enumerate(results[:10], 1):
            year = movie.get("release_date", "")[:4] if movie.get("release_date") else "????"
            rating = movie.get("vote_average", 0)
            log(f"    {i}. {movie.get('title')} ({year}) - Rating: {rating}/10")

    return results


# ---------------------------------------------------------
# Search a single movie by title
# ---------------------------------------------------------
def search_movie_by_title(title, min_rating=0):
    try:
        resp = movie_client.search(title)
    except Exception as e:
        return None, f"[X] Error searching for '{title}': {e}"

    if not resp:
        return None, f"[X] Not found on TMDB: {title}"

    movie = resp[0]
    rating = getattr(movie, "vote_average", 0) or 0

    if rating >= min_rating:
        year = getattr(movie, "release_date", "")[:4] if getattr(movie, "release_date", None) else "????"
        return movie.__dict__, f"[+] Found: {movie.title} ({year}) - Rating: {rating}/10"
    else:
        return None, f"[X] Skipped: {movie.title} (rating {rating} < {min_rating})"


# ---------------------------------------------------------
# Parallel search over many titles
# ---------------------------------------------------------
def search_movies_parallel(titles, min_rating=0):
    results = []
    seen_ids = set()

    with ThreadPoolExecutor(max_workers=config.TMDB_PARALLEL_REQUESTS) as executor:
        future_to_title = {
            executor.submit(search_movie_by_title, title, min_rating): title
            for title in titles
        }

        for future in as_completed(future_to_title):
            movie, msg = future.result()
            log(f"    {msg}")

            if movie:
                movie_id = movie.get("id")
                if movie_id not in seen_ids:
                    results.append(movie)
                    seen_ids.add(movie_id)

    return results, seen_ids