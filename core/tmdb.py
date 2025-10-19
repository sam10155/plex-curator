#!/usr/bin/env python3
import tmdbsimple as tmdb
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.utils import log
import config

tmdb.API_KEY = config.TMDB_KEY

def search_by_keywords(keywords, max_results=1000, min_rating=0):
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
            log(f"[X] TMDB search error for '{kw}': {e}")
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

def search_movie_by_title(title, min_rating=0):
    try:
        search = tmdb.Search()
        resp = search.movie(query=title)
        results = resp.get("results", [])
        
        if results:
            movie = results[0]
            rating = movie.get("vote_average") or 0
            
            if rating >= min_rating:
                year = movie.get("release_date", "")[:4] if movie.get("release_date") else "????"
                return movie, f"[+] Found: {movie.get('title')} ({year}) - Rating: {rating}/10"
            else:
                return None, f"[X] Skipped: {movie.get('title')} (rating {rating} < {min_rating})"
        else:
            return None, f"[X] Not found on TMDB: {title}"
    except Exception as e:
        return None, f"[X] Error searching for '{title}': {e}"

def search_movies_parallel(titles, min_rating=0):
    results = []
    seen_ids = set()
    
    with ThreadPoolExecutor(max_workers=config.TMDB_PARALLEL_REQUESTS) as executor:
        future_to_title = {executor.submit(search_movie_by_title, title, min_rating): title for title in titles}
        
        for future in as_completed(future_to_title):
            movie, msg = future.result()
            log(f"    {msg}")
            
            if movie:
                movie_id = movie.get("id")
                if movie_id not in seen_ids:
                    results.append(movie)
                    seen_ids.add(movie_id)
    
    return results, seen_ids