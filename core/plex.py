#!/usr/bin/env python3
from difflib import SequenceMatcher
from plexapi.server import PlexServer
from core.utils import log, normalize_title
import config

class PlexLibraryCache:
    def __init__(self, plex):
        self.plex = plex
        self._cache = None
    
    def get_movies(self):
        if self._cache is None:
            self._cache = self.plex.library.section("Movies").all()
            log(f"[-] Loaded {len(self._cache)} movies from Plex library")
        return self._cache
    
    def get_normalized_map(self):
        if not hasattr(self, '_normalized_map'):
            movies = self.get_movies()
            self._normalized_map = {normalize_title(m.title): m for m in movies}
        return self._normalized_map

def connect():
    return PlexServer(config.PLEX_URL, config.PLEX_TOKEN)

def find_movies(tmdb_movies, plex_cache, keywords, ai_count_hint=0):
    plex_movies = plex_cache.get_movies()
    plex_map = plex_cache.get_normalized_map()
    
    matched = []
    ai_matched_count = 0
    
    log(f"[-] Searching Plex library with {len(tmdb_movies)} TMDB candidates")

    for idx, tmdb_movie in enumerate(tmdb_movies):
        tmdb_title = normalize_title(tmdb_movie.get("title", ""))
        if tmdb_title in plex_map:
            plex_movie = plex_map[tmdb_title]
            if plex_movie not in matched:
                matched.append(plex_movie)
                if idx < ai_count_hint:
                    ai_matched_count += 1
                    log(f"    [+] AI Match: {plex_movie.title}")
                else:
                    log(f"    [+] Keyword Match: {plex_movie.title}")
        if len(matched) >= config.MAX_COLLECTION_ITEMS:
            break

    if len(matched) < config.MAX_COLLECTION_ITEMS:
        log(f"[-] Found {ai_matched_count} AI matches, {len(matched) - ai_matched_count} keyword matches")
        log(f"[-] Need {config.MAX_COLLECTION_ITEMS - len(matched)} more, using keyword fallback...")
        
        scored = []
        for movie in plex_movies:
            if movie in matched:
                continue
                
            searchable = " ".join([
                movie.title or "",
                getattr(movie, "summary", "") or "",
                " ".join([g.tag for g in getattr(movie, "genres", [])])
            ]).lower()

            hit_count = sum(1 for kw in keywords if kw.lower() in searchable)
            if hit_count == 0:
                continue

            fuzz_score = max(
                SequenceMatcher(None, normalize_title(movie.title), normalize_title(kw)).ratio()
                for kw in keywords
            )

            total_score = (hit_count * 20) + (fuzz_score * 100)
            if total_score >= 70:
                scored.append((total_score, movie))

        scored.sort(key=lambda x: x[0], reverse=True)
        for score, movie in scored:
            if movie not in matched:
                matched.append(movie)
                log(f"    [+] Keyword Match (score: {score:.1f}): {movie.title}")
            if len(matched) >= config.MAX_COLLECTION_ITEMS:
                break

    matched = [m for m in matched if hasattr(m, "ratingKey")]
    log(f"[-] Final: {ai_matched_count}/{len(matched)} from AI, {len(matched) - ai_matched_count} from keywords")
    
    return matched[:config.MAX_COLLECTION_ITEMS], ai_matched_count

def create_collection(plex, name, items, ai_count):
    items = [i for i in items if hasattr(i, "ratingKey") and getattr(i, "ratingKey")]
    if not items:
        log(f"[X] No valid items for collection '{name}'")
        return None
    
    log(f"[-] Creating collection with {len(items)} items ({ai_count} AI, {len(items) - ai_count} keywords)")

    try:
        movies_section = plex.library.section("Movies")
    except Exception as e:
        log(f"[X] Failed to get Movies library: {e}")
        raise

    try:
        for collection in movies_section.collections():
            if collection.title == name:
                log(f"[-] Deleting existing collection: {name}")
                collection.delete()
                break
    except Exception as e:
        log(f"[X] Error checking existing collections: {e}")

    try:
        items[0].addCollection(name)
        for item in items[1:]:
            item.addCollection(name)
        
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
                log(f"[+] Collection '{name}' created!")
                log(f"    - Total movies: {len(items)}")
                log(f"    - AI-curated: {ai_count}")
                log(f"    - Keyword-matched: {len(items) - ai_count}")
                log(f"[-] Promotion error: {e}")
            
            return collection
        else:
            log(f"[X] Collection created but couldn't retrieve it")
            return None
            
    except Exception as e:
        log(f"[X] Failed to create collection: {e}")
        raise