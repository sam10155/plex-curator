#!/usr/bin/env python3
"""
Pure episode-block assembly logic for TV channels.

Operates on plain episode records (dicts) so it can be unit-tested without
plexapi or a live server:

    {"key", "show_key", "show_title", "season", "episode", "title", "duration_ms"}
"""
import re

DEFAULT_EPISODE_MS = 22 * 60 * 1000

_PART_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_PART_RE = re.compile(r'\bpart\s*[\s\-]?(\d+|one|two|three|four|five)\b', re.IGNORECASE)
_TRAILING_NUM_RE = re.compile(r'\((\d+)\)\s*$')
# Prefix must be this long to count as a shared multi-part title ("Partners
# in Crime" / "Party Down" must never group with anything).
_MIN_PREFIX = 5


def _part_info(title):
    """Return (prefix, part_number) if the title looks like one part of a
    multi-part episode, else (None, None)."""
    title = title or ""
    m = _TRAILING_NUM_RE.search(title)
    if m:
        prefix = title[:m.start()].strip(" -:,.")
        if len(prefix) >= _MIN_PREFIX:
            return prefix.lower(), int(m.group(1))
    m = _PART_RE.search(title)
    if m:
        num = m.group(1).lower()
        num = int(num) if num.isdigit() else _PART_WORDS[num]
        prefix = title[:m.start()].strip(" -:,.(")
        if len(prefix) >= _MIN_PREFIX:
            return prefix.lower(), num
    return None, None


def _consecutive(prev, cur):
    """True if cur directly follows prev in airing order."""
    if prev["season"] == cur["season"]:
        return cur["episode"] == prev["episode"] + 1
    # allow a two-parter spanning a season boundary (finale -> premiere)
    return cur["season"] == prev["season"] + 1 and cur["episode"] == 1


def detect_multipart_groups(episodes):
    """Group a show's chronologically sorted episode list into units.

    Each unit is a list of one or more episodes; multi-part episodes
    (consecutive episodes sharing a title prefix with ascending part
    numbers) form a single unit so they are always played together.
    """
    units = []
    for ep in episodes:
        if units:
            prev = units[-1][-1]
            prev_prefix, prev_num = _part_info(prev.get("title", ""))
            cur_prefix, cur_num = _part_info(ep.get("title", ""))
            if (prev_prefix is not None
                    and cur_prefix == prev_prefix
                    and cur_num == prev_num + 1
                    and _consecutive(prev, ep)):
                units[-1].append(ep)
                continue
        units.append([ep])
    return units


def unit_duration(unit, default_ms=DEFAULT_EPISODE_MS):
    return sum(ep.get("duration_ms") or default_ms for ep in unit)


def select_shows_for_block(candidates, history, count):
    """Pick `count` shows from LLM-approved candidates, rotating away from
    the shows used in the previous block and preferring least-recently /
    least-often used shows. `history` is one channel's history dict."""
    history = history or {}
    shows_hist = history.get("shows", {})
    last_block = set(history.get("last_block_shows", []))

    def sort_key(c):
        key = str(c["key"])
        h = shows_hist.get(key, {})
        return (
            1 if key in last_block else 0,
            h.get("last_used") or "",
            h.get("times_used", 0),
        )

    return sorted(candidates, key=sort_key)[:count]


def _next_unit_index(units, pos, recent_keys, used, preferred_keys=None):
    """Find the next playable unit index for a show, scanning forward from
    pos (wrapping). Preferred units (seasonal/AI-boosted episodes) win
    first, then any unit not recently played; recently played units become
    eligible only when nothing else is left (the show has wrapped)."""
    n = len(units)
    if preferred_keys:
        for i in range(n):
            idx = (pos + i) % n
            if idx in used:
                continue
            if all(ep["key"] in recent_keys for ep in units[idx]):
                continue
            if any(ep["key"] in preferred_keys for ep in units[idx]):
                return idx
    for i in range(n):
        idx = (pos + i) % n
        if idx in used:
            continue
        if all(ep["key"] in recent_keys for ep in units[idx]):
            continue
        return idx
    for i in range(n):
        idx = (pos + i) % n
        if idx not in used:
            return idx
    return None


def assemble_block(show_units, cursors, target_ms, max_ms,
                   recent_keys=None, show_order=None,
                   default_ms=DEFAULT_EPISODE_MS, preferred_keys=None):
    """Assemble an ordered episode block from multiple shows.

    show_units: {show_key: [unit, ...]} from detect_multipart_groups
    cursors:    {show_key: starting unit index} from channel history
    show_order: rotation order for the round-robin (defaults to dict order)

    Round-robins one unit per show per pass, so the same show is never
    adjacent to itself except inside a multi-part unit. Stops once total
    duration reaches target_ms, never exceeds max_ms, and stops early if
    only one show has material left (continuing would force adjacency).

    Returns (episodes, consumption) where consumption is
    {show_key: {"next_index": int, "episode_keys": [str, ...]}}
    for every show that contributed at least one unit.
    """
    recent_keys = set(recent_keys or [])
    preferred_keys = set(preferred_keys or [])
    order = [k for k in (show_order or list(show_units)) if show_units.get(k)]

    pos = {k: cursors.get(k, 0) % len(show_units[k]) for k in order}
    used = {k: set() for k in order}
    consumption = {}

    episodes = []
    total = 0
    last_show = None
    active = list(order)

    while total < target_ms and active:
        progressed = False
        for show_key in list(active):
            if total >= target_ms:
                break
            units = show_units[show_key]
            idx = _next_unit_index(units, pos[show_key], recent_keys,
                                   used[show_key], preferred_keys)
            if idx is None:
                active.remove(show_key)
                continue
            if last_show == show_key:
                # only happens when this is the sole remaining show
                continue
            unit = units[idx]
            dur = unit_duration(unit, default_ms)
            if total + dur > max_ms:
                continue
            episodes.extend(unit)
            used[show_key].add(idx)
            pos[show_key] = (idx + 1) % len(units)
            entry = consumption.setdefault(show_key, {"next_index": 0, "episode_keys": []})
            entry["next_index"] = pos[show_key]
            entry["episode_keys"].extend(ep["key"] for ep in unit)
            total += dur
            last_show = show_key
            progressed = True
        if not progressed:
            break

    return episodes, consumption
