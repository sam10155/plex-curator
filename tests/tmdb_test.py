import sys
import os
from tmdbv3api import TMDb, Movie
from core.tmdb import search_by_keywords, search_movie_by_title, search_movies_parallel

import config

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

tmdb = TMDb()
tmdb.api_key = config.TMDB_KEY
tmdb.language = "en"
tmdb.debug = False # Verbose debug

def test_search_by_keywords(verbose=True):
    """Test search_by_keywords function. Returns True if successful."""
    try:
        if verbose:
            print("\n--- Testing search_by_keywords ---")
        keywords = ["Inception", "Matrix"]
        results = search_by_keywords(keywords, max_results=5)
        if verbose:
            print(f"Found {len(results)} movies.")
            for movie in results[:3]:
                print(f"  - {movie.get('title')} ({movie.get('release_date')})")
        return len(results) > 0
    except Exception as e:
        if verbose:
            print(f"[X] Test failed: {e}")
        return False

def test_search_movie_by_title(verbose=True):
    """Test search_movie_by_title function. Returns True if successful."""
    try:
        if verbose:
            print("\n--- Testing search_movie_by_title ---")
        title = "Interstellar"
        movie, msg = search_movie_by_title(title)
        if verbose:
            print(msg)
            if movie:
                print(f"  - ID: {movie.get('id')}")
        return movie is not None
    except Exception as e:
        if verbose:
            print(f"[X] Test failed: {e}")
        return False

def test_search_movies_parallel(verbose=True):
    """Test search_movies_parallel function. Returns True if successful."""
    try:
        if verbose:
            print("\n--- Testing search_movies_parallel ---")
        titles = ["Avatar", "Titanic", "The Godfather"]
        results, seen_ids = search_movies_parallel(titles)
        if verbose:
            print(f"Found {len(results)} movies from parallel search.")
            for movie in results:
                print(f"  - {movie.get('title')}")
        return len(results) > 0
    except Exception as e:
        if verbose:
            print(f"[X] Test failed: {e}")
        return False

def run_all_tests(verbose=True):
    """Run all TMDB tests. Returns True if all pass, False otherwise."""
    if verbose:
        print("Running TMDB API tests...")
    
    results = {
        'search_by_keywords': test_search_by_keywords(verbose),
        'search_movie_by_title': test_search_movie_by_title(verbose),
        'search_movies_parallel': test_search_movies_parallel(verbose)
    }
    
    all_passed = all(results.values())
    
    if verbose:
        print("\n" + "=" * 50)
        if all_passed:
            print("✓ All TMDB tests passed")
        else:
            print("✗ Some TMDB tests failed:")
            for test_name, passed in results.items():
                status = "✓" if passed else "✗"
                print(f"  {status} {test_name}")
        print("=" * 50)
    
    return all_passed

if __name__ == "__main__":
    success = run_all_tests(verbose=True)
    sys.exit(0 if success else 1)