#!/usr/bin/env python3
"""
TV channel curation pipeline.

A "channel" is a weekly-regenerated Plex playlist: an LLM picks shows from
the library that fit the channel's theme, then a block of 4-6 hours of
episodes is assembled with no same-show back-to-back episodes (multi-part
episodes excepted) and per-channel rotation history so successive runs
advance through seasons instead of repeating.

Usage: python3 src/channels.py <channel_name>
"""
import os
import sys
import yaml
import config
from core.utils import log
from core.ai import suggest_shows, suggest_episodes
from core.plex import connect
from core.tv import (TVLibraryCache, show_summary_record, get_episode_records,
                     create_or_replace_playlist)
from core.tmdb import enrich_shows
from core.blocks import (detect_multipart_groups, select_shows_for_block,
                         assemble_block, filter_show_candidates)
from core.history import load_channel_history, update_channel_history


def load_channel_config(channel_name):
    channel_file = os.path.join(config.CHANNELS_DIR, f"{channel_name}.yaml")
    if not os.path.exists(channel_file):
        return None
    with open(channel_file, "r") as f:
        return yaml.safe_load(f) or {}


def _candidate_sort_key(record):
    return record.get("tmdb_rating") or record.get("rating") or 0


def run_channel(channel_name, dry_run=False):
    log("=" * 70)
    log(f"RUNNING TV CHANNEL: {channel_name}" + (" (DRY RUN)" if dry_run else ""))
    log("=" * 70)

    cfg = load_channel_config(channel_name)
    if cfg is None:
        log(f"[X] Channel config not found: {channel_name}")
        return False

    playlist_name = cfg.get("playlist_name", channel_name.replace("_", " ").title())
    theme_prompt = cfg.get("prompt", "")
    target_hours = float(cfg.get("target_hours", config.DEFAULT_TARGET_HOURS))
    max_hours = float(cfg.get("max_hours", config.DEFAULT_MAX_HOURS))
    shows_per_block = int(cfg.get("shows_per_block", config.DEFAULT_SHOWS_PER_BLOCK))
    genre_hints = cfg.get("genre_hints", [])
    exclude_genres = cfg.get("exclude_genres", [])
    min_episodes = int(cfg.get("min_episodes", 0) or 0)
    exclude_single_season = bool(cfg.get("exclude_single_season", False))
    sequential = bool(cfg.get("sequential", False))
    section_name = cfg.get("library_section")
    prefer_unwatched = cfg.get("prefer_unwatched", True)
    episode_keywords = [k.lower() for k in cfg.get("episode_keywords", []) if k]
    episode_level_ai = bool(cfg.get("episode_level_ai", False))

    log(f"[-] Playlist: {playlist_name}")
    log(f"[-] Block: {target_hours}h target, {max_hours}h max, {shows_per_block} shows")

    plex = connect()
    tv_cache = TVLibraryCache(plex, section_name)
    shows = tv_cache.get_shows()
    if not shows:
        log("[X] No TV shows found in the Plex library")
        return False

    log("STEP 1: Building show candidate list...")
    log("-" * 70)
    records = [show_summary_record(s) for s in shows]
    records = [r for r in records if r["episode_count"] > 0]
    before = len(records)
    records = filter_show_candidates(
        records, genre_hints=genre_hints, exclude_genres=exclude_genres,
        min_episodes=min_episodes, exclude_single_season=exclude_single_season,
        min_needed=shows_per_block * 2)
    log(f"[-] Filters kept {len(records)}/{before} shows "
        f"(genres={genre_hints or 'any'}, exclude={exclude_genres or 'none'}, "
        f"min_episodes={min_episodes}, exclude_single_season={exclude_single_season})")
    records.sort(key=_candidate_sort_key, reverse=True)
    records = records[:config.MAX_SHOW_CANDIDATES]
    log(f"[-] {len(records)} candidate shows")

    log("STEP 2: TMDB TV enrichment...")
    log("-" * 70)
    records = enrich_shows(records)

    log("STEP 3: Asking AI to pick shows for the theme...")
    log("-" * 70)
    want = shows_per_block * 2
    picked = suggest_shows(theme_prompt, records, want) if theme_prompt.strip() else []
    if picked:
        log(f"[-] AI picked {len(picked)} shows: {', '.join(p['title'] for p in picked)}")
    # Guarantee a full rotation pool even if the model under-delivers —
    # otherwise a 2-item answer produces a 2-show channel forever
    if len(picked) < want:
        picked_keys = {p["key"] for p in picked}
        extras = [r for r in sorted(records, key=_candidate_sort_key, reverse=True)
                  if r["key"] not in picked_keys][:want - len(picked)]
        if extras:
            log(f"[-] AI supplied {len(picked)}/{want}; topping up with "
                f"{len(extras)} top-rated candidates: {', '.join(e['title'] for e in extras)}")
            picked.extend(extras)

    log("STEP 4: Rotating shows and assembling the episode block...")
    log("-" * 70)
    history = load_channel_history(channel_name, config.CHANNEL_HISTORY_FILE)
    selected = select_shows_for_block(picked, history, shows_per_block)
    log(f"[-] This week's lineup: {', '.join(s['title'] for s in selected)}")

    show_map = {str(s.ratingKey): s for s in shows}
    show_units = {}
    titles = {}
    all_episode_records = []
    for record in selected:
        show = show_map.get(record["key"])
        if show is None:
            continue
        episodes = get_episode_records(show)
        if episodes:
            show_units[record["key"]] = detect_multipart_groups(episodes)
            titles[record["key"]] = record["title"]
            all_episode_records.extend(episodes)

    if not show_units:
        log("[X] No episodes found for the selected shows")
        return False

    # Soft-skip pool: rotation history, plus already-watched episodes when
    # prefer_unwatched is on. Both become eligible again once a show has
    # nothing fresh left.
    recent_keys = set(history.get("recent_episode_keys", []))
    if prefer_unwatched:
        watched = {e["key"] for e in all_episode_records if e.get("watched")}
        if watched:
            log(f"[-] Deprioritizing {len(watched)} already-watched episodes")
            recent_keys |= watched

    # Preference pool: seasonal keyword matches and/or episode-level AI picks
    preferred_keys = set()
    if episode_keywords:
        preferred_keys |= {e["key"] for e in all_episode_records
                           if any(kw in e["title"].lower() for kw in episode_keywords)}
        log(f"[-] Keyword boost: {len(preferred_keys)} episodes match {episode_keywords[:5]}")
    if episode_level_ai and theme_prompt.strip():
        candidates = all_episode_records[:config.MAX_EPISODE_CANDIDATES]
        preferred_keys |= suggest_episodes(theme_prompt, candidates)

    if sequential:
        # Strict airing order per show: no skips, no boosts — each week
        # simply continues from where the cursors left off
        log("[-] Sequential mode: episodes play in strict airing order")
        recent_keys = set()
        preferred_keys = set()

    hist_shows = history.get("shows", {})
    cursors = {k: hist_shows.get(k, {}).get("next_index", 0) for k in show_units}
    episodes, consumption = assemble_block(
        show_units,
        cursors,
        target_ms=int(target_hours * 3600 * 1000),
        max_ms=int(max_hours * 3600 * 1000),
        recent_keys=recent_keys,
        show_order=[r["key"] for r in selected if r["key"] in show_units],
        preferred_keys=preferred_keys,
    )

    if not episodes:
        log("[X] Could not assemble an episode block")
        return False

    total_min = sum((e.get("duration_ms") or 0) for e in episodes) // 60000
    log(f"[-] Assembled {len(episodes)} episodes (~{total_min} min):")
    for e in episodes:
        log(f"    {e['show_title']} S{e['season']:02d}E{e['episode']:02d} - {e['title']}")

    if dry_run:
        log("STEP 5: DRY RUN — playlist not created, history not advanced")
        log("-" * 70)
    else:
        log("STEP 5: Creating Plex playlist...")
        log("-" * 70)
        create_or_replace_playlist(plex, playlist_name, [e["_item"] for e in episodes])

        for key, info in consumption.items():
            info["title"] = titles.get(key, "")
        update_channel_history(channel_name, consumption, config.CHANNEL_HISTORY_FILE)

    log("=" * 70)
    log("[+] SUCCESS!" + (" (dry run)" if dry_run else ""))
    log("=" * 70)
    return True


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if not args:
        print("Usage: python3 src/channels.py <channel_name> [--dry-run]")
        sys.exit(1)
    try:
        success = run_channel(args[0], dry_run="--dry-run" in sys.argv)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("\n[X] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"\n[X] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
