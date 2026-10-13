#!/usr/bin/env python3
"""Plex TV library access for channel curation."""
from core.utils import log


class TVLibraryCache:
    def __init__(self, plex, section_name=None):
        self.plex = plex
        self.section_name = section_name
        self._cache = None

    def get_shows(self):
        if self._cache is None:
            shows = []
            if self.section_name:
                sections = [self.plex.library.section(self.section_name)]
            else:
                sections = [s for s in self.plex.library.sections() if s.type == 'show']
            for section in sections:
                shows.extend(section.all())
            self._cache = shows
            log(f"[-] Loaded {len(shows)} shows from {len(sections)} TV section(s)")
        return self._cache


def show_summary_record(show):
    """Lightweight metadata record for LLM candidate lists. Uses leafCount
    for the episode count — never enumerates episodes library-wide."""
    return {
        "key": str(show.ratingKey),
        "title": show.title,
        "year": getattr(show, "year", None),
        "genres": [g.tag for g in getattr(show, "genres", []) or []],
        "content_rating": getattr(show, "contentRating", None),
        "summary": (getattr(show, "summary", "") or "")[:200],
        "episode_count": getattr(show, "leafCount", 0) or 0,
        "rating": getattr(show, "audienceRating", None),
    }


def get_episode_records(show, include_specials=False):
    """Fetch a show's episodes as plain records sorted in airing order.
    The plexapi object rides along in '_item' for playlist creation but is
    never serialized."""
    records = []
    for ep in show.episodes():
        season = ep.seasonNumber or 0
        if season == 0 and not include_specials:
            continue
        records.append({
            "key": str(ep.ratingKey),
            "show_key": str(show.ratingKey),
            "show_title": show.title,
            "season": season,
            "episode": ep.episodeNumber or 0,
            "title": ep.title or "",
            "duration_ms": getattr(ep, "duration", None),
            "watched": bool(getattr(ep, "viewCount", 0) or 0),
            "_item": ep,
        })
    records.sort(key=lambda r: (r["season"], r["episode"]))
    return records


def create_or_replace_playlist(plex, name, items):
    """Replace a playlist by name. The non-empty check happens BEFORE the
    old playlist is deleted so a failed assembly never destroys last
    week's block."""
    if not items:
        raise ValueError(f"Refusing to replace playlist '{name}' with an empty block")

    for playlist in plex.playlists():
        if playlist.title == name:
            log(f"[-] Deleting existing playlist: {name}")
            playlist.delete()
            break

    playlist = plex.createPlaylist(title=name, items=items)
    log(f"[+] Playlist '{name}' created with {len(items)} episodes")
    return playlist
