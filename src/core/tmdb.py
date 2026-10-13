#!/usr/bin/env python3
from tmdbv3api import TMDb, Movie, TV, Discover
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.utils import log, normalize_title, load_json_file, save_json_file
import config

# -------------------------
# TMDb Initialization
# -------------------------
tmdb = TMDb()
tmdb.api_key = config.TMDB_KEY
tmdb.language = "en"
tmdb.debug = False # For verbosity, TODO: make flag set at runtime

movie_client = Movie()
discover_client = Discover()

try:
    tv_client = TV() if config.TMDB_KEY else None
except Exception:
    tv_client = None


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
# Discover — structured filters instead of keyword search
# (e.g. {"origin_country": "CA"} for Canadian films)
# ---------------------------------------------------------

# TMDB's movie genre ids are static; map friendly names to them
GENRE_IDS = {
    "action": 28, "adventure": 12, "animation": 16, "comedy": 35,
    "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
    "fantasy": 14, "history": 36, "horror": 27, "music": 10402,
    "mystery": 9648, "romance": 10749, "science fiction": 878,
    "sci-fi": 878, "scifi": 878, "tv movie": 10770, "thriller": 53,
    "war": 10752, "western": 37,
}

# Friendly YAML/form keys and how they translate to TMDB Discover params.
# Anything NOT in this map is passed straight through, so raw TMDB keys
# (with_origin_country, vote_count.gte, ...) keep working too.
def build_discover_params(cfg):
    params = {}
    cfg = dict(cfg or {})

    country = cfg.pop("origin_country", None)
    if country:
        params["with_origin_country"] = str(country).upper()

    language = cfg.pop("language", None)
    if language:
        params["with_original_language"] = str(language).lower()

    genres = cfg.pop("genres", None)
    if genres:
        if isinstance(genres, str):
            genres = [g.strip() for g in genres.split(",") if g.strip()]
        ids = []
        for g in genres:
            gid = GENRE_IDS.get(str(g).strip().lower())
            if gid:
                ids.append(str(gid))
            elif str(g).strip().isdigit():
                ids.append(str(g).strip())
            else:
                log(f"[X] Unknown TMDB genre ignored: {g}")
        if ids:
            params["with_genres"] = "|".join(ids)  # pipe = any-of

    year_from = cfg.pop("year_from", None)
    if year_from:
        params["primary_release_date.gte"] = f"{int(year_from)}-01-01"
    year_to = cfg.pop("year_to", None)
    if year_to:
        params["primary_release_date.lte"] = f"{int(year_to)}-12-31"

    min_votes = cfg.pop("min_votes", None)
    if min_votes:
        params["vote_count.gte"] = int(min_votes)

    params.update(cfg)  # raw TMDB keys pass through untouched
    return params


def discover_movies(params, max_results=200, min_rating=0):
    base = build_discover_params(params)
    base.setdefault("sort_by", "popularity.desc")
    if min_rating:
        base.setdefault("vote_average.gte", min_rating)

    results = []
    seen_ids = set()
    page = 1
    while len(results) < max_results and page <= 25:
        base["page"] = page
        try:
            resp = discover_client.discover_movies(base)
        except Exception as e:
            log(f"[X] TMDB discover error (page {page}): {e}")
            break

        batch = list(resp or [])
        if not batch:
            break

        for r in batch:
            movie_id = getattr(r, "id", None)
            if movie_id is None or movie_id in seen_ids:
                continue
            rating = getattr(r, "vote_average", 0) or 0
            if rating < min_rating:
                continue
            results.append(r.__dict__)
            seen_ids.add(movie_id)
            if len(results) >= max_results:
                break
        page += 1

    log(f"[-] TMDB Discover found {len(results)} movies for filters {params}")
    if results:
        log("[-] First 10 Discover results:")
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

    movie = next(iter(resp), None)

    if movie is None:
        return None, f"[X] Not found on TMDB: {title}"

    if isinstance(movie, str):
        return None, f"[X] Invalid TMDB result for '{title}': got string"

    rating = getattr(movie, "vote_average", 0) or 0
    movie_title = getattr(movie, "title", None)

    if callable(movie_title):
        movie_title = None
    
    if not movie_title:
        movie_title = title
    
    if rating >= min_rating:
        year = (
            getattr(movie, "release_date", "")[:4]
            if getattr(movie, "release_date", None)
            else "????"
        )

        return (
            movie.__dict__,
            f"[+] Found: {movie_title} ({year}) - Rating: {rating}/10"
        )

    else:
        return (
            None,
            f"[X] Skipped: {movie_title} (rating {rating} < {min_rating})"
        )


# ---------------------------------------------------------
# Parallel search over many titles
# ---------------------------------------------------------
def search_movies_parallel(titles, min_rating=0):
    titles = list(dict.fromkeys(
        t.strip() for t in titles if t.strip()
    ))
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


# ---------------------------------------------------------
# TV show enrichment (external rating/popularity signal)
# ---------------------------------------------------------
def _search_tv_show(title):
    try:
        resp = tv_client.search(title)
        show = next(iter(resp), None)
        if show is None or isinstance(show, str):
            return {}
        return {
            "rating": getattr(show, "vote_average", None),
            "popularity": getattr(show, "popularity", None),
        }
    except Exception as e:
        log(f"[X] TMDB TV search error for '{title}': {e}")
        return {}


def enrich_shows(show_records):
    """Attach tmdb_rating/tmdb_popularity to show records in place.
    Degrades gracefully: with no key or on any error, records are simply
    returned without enrichment."""
    if tv_client is None:
        log("[-] TMDB TV enrichment skipped (no TMDB key)")
        return show_records

    cache = load_json_file(config.TMDB_TV_CACHE_FILE)
    to_fetch = {normalize_title(r["title"]): r["title"] for r in show_records
                if normalize_title(r["title"]) not in cache}

    if to_fetch:
        log(f"[-] Enriching {len(to_fetch)} shows via TMDB TV search...")
        with ThreadPoolExecutor(max_workers=config.TMDB_PARALLEL_REQUESTS) as executor:
            futures = {executor.submit(_search_tv_show, title): norm
                       for norm, title in to_fetch.items()}
            for future in as_completed(futures):
                cache[futures[future]] = future.result()
        try:
            save_json_file(config.TMDB_TV_CACHE_FILE, cache)
        except OSError as e:
            log(f"[X] Could not save TMDB TV cache: {e}")

    enriched = 0
    for record in show_records:
        info = cache.get(normalize_title(record["title"])) or {}
        if info.get("rating"):
            record["tmdb_rating"] = info["rating"]
            enriched += 1
        if info.get("popularity"):
            record["tmdb_popularity"] = info["popularity"]
    log(f"[-] TMDB TV enrichment: {enriched}/{len(show_records)} shows have external ratings")
    return show_records