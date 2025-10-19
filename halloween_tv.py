#!/usr/bin/env python3
"""
Quick script to create a Plex playlist of all Halloween-themed TV episodes
"""
import os
from plexapi.server import PlexServer
from plexapi.playlist import Playlist

PLEX_URL = os.getenv("PLEX_URL", "http://localhost:32400")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
PLAYLIST_NAME = "Halloween TV Episodes"

HALLOWEEN_KEYWORDS = [
    "halloween",
    "trick or treat",
    "spooky",
    "haunted",
    "ghost",
    "monster",
    "vampire",
    "zombie",
    "witch",
    "costume",
    "candy",
    "pumpkin",
    "scary",
    "creepy",
    "horror"
]

def find_halloween_episodes(plex):
    """Find all TV episodes with Halloween themes"""
    print("Searching for Halloween-themed TV episodes...")
    halloween_episodes = []
    
    tv_sections = [s for s in plex.library.sections() if s.type == 'show']
    
    if not tv_sections:
        print("[X] No TV show libraries found!")
        return []
    
    print(f"[-] Found {len(tv_sections)} TV library/libraries")
    
    for section in tv_sections:
        print(f"\n[-] Scanning library: {section.title}")
        shows = section.all()
        print(f"    Total shows: {len(shows)}")
        
        for show in shows:
            try:
                episodes = show.episodes()
                
                for episode in episodes:
                    title_lower = episode.title.lower()
                    
                    if any(keyword in title_lower for keyword in HALLOWEEN_KEYWORDS):
                        halloween_episodes.append(episode)
                        season_ep = f"S{episode.seasonNumber:02d}E{episode.episodeNumber:02d}"
                        print(f"    [+] {show.title} - {season_ep} - {episode.title}")
                        
            except Exception as e:
                print(f"    [X] Error scanning {show.title}: {e}")
                continue
    
    return halloween_episodes


def create_playlist(plex, episodes):
    """Create or update the Halloween playlist"""
    if not episodes:
        print("\n[X] No Halloween episodes found!")
        return
    
    print(f"\n[-] Found {len(episodes)} Halloween episodes total")
    
    for playlist in plex.playlists():
        if playlist.title == PLAYLIST_NAME:
            print(f"[-] Deleting existing playlist: {PLAYLIST_NAME}")
            playlist.delete()
            break
    
    
    try:
        episodes.sort(key=lambda e: (
            e.grandparentTitle, 
            e.seasonNumber,
            e.episodeNumber
        ))
        
        playlist = plex.createPlaylist(title=PLAYLIST_NAME, items=episodes)
        print(f"\n[+] Playlist '{PLAYLIST_NAME}' created successfully!")
        print(f"    Total episodes: {len(episodes)}")
        
        show_counts = {}
        for ep in episodes:
            show_name = ep.grandparentTitle
            show_counts[show_name] = show_counts.get(show_name, 0) + 1
        
        print("\n[-] Episodes by show:")
        for show, count in sorted(show_counts.items()):
            print(f"    {show}: {count} episode(s)")
            
        return playlist
        
    except Exception as e:
        print(f"[X] Failed to create playlist: {e}")
        raise


def main():
    if not PLEX_TOKEN:
        print("[X] PLEX_TOKEN environment variable not set!")
        print("    Set it with: export PLEX_TOKEN='your-token-here'")
        return
    
    print("=" * 70)
    print("HALLOWEEN TV EPISODES PLAYLIST CREATOR")
    print("=" * 70)
    
    try:
        plex = PlexServer(PLEX_URL, PLEX_TOKEN)
        print(f"[-] Connected to Plex server: {plex.friendlyName}")
    except Exception as e:
        print(f"[X] Failed to connect to Plex: {e}")
        return
    
    episodes = find_halloween_episodes(plex)
    
    if episodes:
        create_playlist(plex, episodes)
        print("\n" + "=" * 70)
        print("[+] DONE!")
        print("=" * 70)
    else:
        print("\n[X] No episodes found. Try adding more keywords or check your library.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[X] Interrupted by user")
    except Exception as e:
        print(f"\n[X] Fatal error: {e}")
        import traceback
        traceback.print_exc()