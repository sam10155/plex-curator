#!/usr/bin/env python3
import sys
import os
import tempfile
import datetime

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.blocks import detect_multipart_groups, assemble_block, select_shows_for_block
from core.history import load_channel_history, update_channel_history


def make_units(show, count):
    eps = [{
        "key": f"{show}-{i}",
        "show_key": show,
        "show_title": show,
        "season": 1,
        "episode": i + 1,
        "title": f"{show} Episode {i + 1}",
        "duration_ms": 22 * 60 * 1000,
    } for i in range(count)]
    return detect_multipart_groups(eps)


def _run_block(channel, path, shows=("a", "b", "c"), count=40,
               target_h=2, now=None):
    history = load_channel_history(channel, path)
    show_units = {s: make_units(s, count) for s in shows}
    hist_shows = history.get("shows", {})
    cursors = {s: hist_shows.get(s, {}).get("next_index", 0) for s in shows}
    episodes, consumption = assemble_block(
        show_units, cursors,
        target_ms=target_h * 3600 * 1000,
        max_ms=(target_h + 1) * 3600 * 1000,
        recent_keys=history.get("recent_episode_keys", []),
    )
    for key, info in consumption.items():
        info["title"] = key
    update_channel_history(channel, consumption, path, now=now)
    return episodes


def test_second_run_differs():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "history.json")
        first = _run_block("test", path)
        second = _run_block("test", path)
        assert first and second
        first_keys = {e["key"] for e in first}
        second_keys = {e["key"] for e in second}
        assert not (first_keys & second_keys), \
            f"second run repeated episodes: {first_keys & second_keys}"
    print("✓ Second run uses different episodes test passed")


def test_cursor_advances():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "history.json")
        _run_block("test", path)
        history = load_channel_history("test", path)
        for show, entry in history["shows"].items():
            assert entry["next_index"] > 0, f"{show} cursor did not advance"
            assert entry["times_used"] == 1
        _run_block("test", path)
        history2 = load_channel_history("test", path)
        for show in history["shows"]:
            assert history2["shows"][show]["next_index"] > history["shows"][show]["next_index"]
            assert history2["shows"][show]["times_used"] == 2
    print("✓ Cursor advancement test passed")


def test_wrap_around_when_exhausted():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "history.json")
        # tiny shows: 4 episodes each, 2h target forces exhaustion + wrap
        for _ in range(3):
            episodes = _run_block("test", path, shows=("a", "b"), count=4,
                                  target_h=1)
            assert episodes, "wrap-around should keep producing episodes"
    print("✓ Wrap-around on exhaustion test passed")


def test_ring_buffer_trimmed():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "history.json")
        consumed = {"a": {"title": "a", "next_index": 1,
                          "episode_keys": [str(i) for i in range(500)]}}
        update_channel_history("test", consumed, path, memory=300)
        history = load_channel_history("test", path)
        assert len(history["recent_episode_keys"]) == 300
        assert history["recent_episode_keys"][-1] == "499"
    print("✓ Ring buffer trim test passed")


def test_last_block_shows_recorded():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "history.json")
        _run_block("test", path, shows=("a", "b", "c"))
        history = load_channel_history("test", path)
        assert set(history["last_block_shows"]) <= {"a", "b", "c"}
        assert history["last_block_shows"], "last_block_shows must be recorded"
    print("✓ last_block_shows recorded test passed")


def test_channels_isolated():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "history.json")
        _run_block("cartoons", path)
        _run_block("drama", path)
        cartoons = load_channel_history("cartoons", path)
        drama = load_channel_history("drama", path)
        assert cartoons and drama
        assert cartoons is not drama
        empty = load_channel_history("missing", path)
        assert empty == {}
    print("✓ Channel isolation test passed")


def test_rotation_prefers_oldest():
    candidates = [{"key": k, "title": k} for k in ("a", "b", "c")]
    history = {
        "last_block_shows": [],
        "shows": {
            "a": {"last_used": "2026-10-10", "times_used": 1},
            "b": {"last_used": "2026-01-01", "times_used": 9},
        },
    }
    selected = select_shows_for_block(candidates, history, 2)
    keys = [c["key"] for c in selected]
    assert keys[0] == "c", "never-used show should come first"
    assert keys[1] == "b", "least-recently-used show should come second"
    print("✓ Rotation prefers oldest test passed")


def run_all_tests():
    print("\nRunning rotation/history tests...")
    print("=" * 50)
    tests = [
        test_second_run_differs,
        test_cursor_advances,
        test_wrap_around_when_exhausted,
        test_ring_buffer_trimmed,
        test_last_block_shows_recorded,
        test_channels_isolated,
        test_rotation_prefers_oldest,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} errored: {e}")
            failed += 1
    print("=" * 50)
    if failed == 0:
        print(f"✓ All {len(tests)} rotation tests passed!")
        return True
    print(f"✗ {failed}/{len(tests)} tests failed")
    return False


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
