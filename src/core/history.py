#!/usr/bin/env python3
"""
Per-channel rotation history, persisted as JSON.

Schema (one top-level key per channel id):
{
  "saturday_morning_cartoons": {
    "last_generated": "2026-10-11T05:00:03",
    "shows": {
      "<plex ratingKey>": {"title": "DuckTales", "next_index": 14,
                           "last_used": "...", "times_used": 3}
    },
    "recent_episode_keys": ["48213", "48214"],
    "last_block_shows": ["<ratingKey>", "..."]
  }
}

File paths are always passed in so tests can use a temp dir. History must
only be advanced after the Plex playlist was created successfully — a
failed run should repeat material, never skip it.
"""
import datetime

from core.utils import load_json_file, save_json_file

RECENT_EPISODE_MEMORY = 300


def load_channel_history(channel_id, path):
    return load_json_file(path).get(channel_id, {})


def update_channel_history(channel_id, consumed, path, now=None,
                           memory=RECENT_EPISODE_MEMORY):
    """Record a successful block generation.

    consumed: {show_key: {"title": str, "next_index": int,
                          "episode_keys": [str, ...]}}
    """
    data = load_json_file(path)
    channel = data.setdefault(channel_id, {})
    now_iso = (now or datetime.datetime.now()).isoformat(timespec="seconds")

    channel["last_generated"] = now_iso
    shows = channel.setdefault("shows", {})
    recent = list(channel.get("recent_episode_keys", []))

    for show_key, info in consumed.items():
        show_key = str(show_key)
        entry = shows.setdefault(show_key, {"times_used": 0})
        if info.get("title"):
            entry["title"] = info["title"]
        entry["next_index"] = info.get("next_index", 0)
        entry["last_used"] = now_iso
        entry["times_used"] = entry.get("times_used", 0) + 1
        recent.extend(str(k) for k in info.get("episode_keys", []))

    channel["recent_episode_keys"] = recent[-memory:]
    channel["last_block_shows"] = [str(k) for k in consumed]

    save_json_file(path, data)
    return channel
