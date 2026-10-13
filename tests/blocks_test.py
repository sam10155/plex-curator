#!/usr/bin/env python3
import sys
import os

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.blocks import (detect_multipart_groups, assemble_block,
                         select_shows_for_block, DEFAULT_EPISODE_MS)


def ep(show, season, episode, title, duration_ms=22*60*1000, key=None):
    return {
        "key": key or f"{show}-s{season}e{episode}",
        "show_key": show,
        "show_title": show,
        "season": season,
        "episode": episode,
        "title": title,
        "duration_ms": duration_ms,
    }


def test_multipart_part_n():
    eps = [
        ep("a", 1, 1, "The Heist Part 1"),
        ep("a", 1, 2, "The Heist Part 2"),
        ep("a", 1, 3, "Normal Episode"),
    ]
    units = detect_multipart_groups(eps)
    assert len(units) == 2, f"expected 2 units, got {len(units)}"
    assert len(units[0]) == 2
    assert units[0][0]["title"] == "The Heist Part 1"
    assert units[0][1]["title"] == "The Heist Part 2"
    print("✓ 'Part 1'/'Part 2' grouping test passed")


def test_multipart_trailing_number():
    eps = [
        ep("a", 2, 5, "The Return (1)"),
        ep("a", 2, 6, "The Return (2)"),
        ep("a", 2, 7, "Something Else"),
    ]
    units = detect_multipart_groups(eps)
    assert len(units) == 2
    assert len(units[0]) == 2
    print("✓ '(1)'/'(2)' grouping test passed")


def test_multipart_word_numbers():
    eps = [
        ep("a", 1, 1, "Grand Finale Part One"),
        ep("a", 1, 2, "Grand Finale Part Two"),
    ]
    units = detect_multipart_groups(eps)
    assert len(units) == 1 and len(units[0]) == 2
    print("✓ 'Part One'/'Part Two' grouping test passed")


def test_no_false_positive_similar_words():
    eps = [
        ep("a", 1, 1, "Partners in Crime"),
        ep("a", 1, 2, "Party Down"),
    ]
    units = detect_multipart_groups(eps)
    assert len(units) == 2, "'Partners'/'Party' must not group"
    print("✓ No false positive on Part-like words test passed")


def test_no_group_different_prefix():
    eps = [
        ep("a", 1, 1, "The Heist Part 1"),
        ep("a", 1, 2, "The Escape Part 2"),
    ]
    units = detect_multipart_groups(eps)
    assert len(units) == 2, "different prefixes must not group"
    print("✓ Different prefix no-group test passed")


def test_no_group_non_consecutive():
    eps = [
        ep("a", 1, 1, "The Heist Part 1"),
        ep("a", 1, 5, "The Heist Part 2"),
    ]
    units = detect_multipart_groups(eps)
    assert len(units) == 2, "non-consecutive episodes must not group"
    print("✓ Non-consecutive no-group test passed")


def test_season_boundary_multipart():
    eps = [
        ep("a", 1, 10, "Cliffhanger Part 1"),
        ep("a", 2, 1, "Cliffhanger Part 2"),
    ]
    units = detect_multipart_groups(eps)
    assert len(units) == 1 and len(units[0]) == 2
    print("✓ Season-boundary multipart test passed")


def _units_for(show, count, start_season=1):
    eps = [ep(show, start_season, i + 1, f"{show} Episode {i + 1}") for i in range(count)]
    return detect_multipart_groups(eps)


def test_no_adjacent_same_show():
    show_units = {s: _units_for(s, 20) for s in ("a", "b", "c")}
    episodes, _ = assemble_block(show_units, {}, target_ms=4 * 3600 * 1000,
                                 max_ms=5 * 3600 * 1000)
    assert episodes, "block should not be empty"
    for prev, cur in zip(episodes, episodes[1:]):
        assert prev["show_key"] != cur["show_key"], \
            f"adjacent same-show episodes: {prev['title']} / {cur['title']}"
    print("✓ No adjacent same-show test passed")


def test_multipart_adjacency_allowed_and_ordered():
    eps_a = [
        ep("a", 1, 1, "Opener"),
        ep("a", 1, 2, "Big Story Part 1"),
        ep("a", 1, 3, "Big Story Part 2"),
        ep("a", 1, 4, "Closer"),
    ]
    show_units = {
        "a": detect_multipart_groups(eps_a),
        "b": _units_for("b", 10),
    }
    episodes, _ = assemble_block(show_units, {}, target_ms=3 * 3600 * 1000,
                                 max_ms=4 * 3600 * 1000)
    titles = [e["title"] for e in episodes]
    i = titles.index("Big Story Part 1")
    assert titles[i + 1] == "Big Story Part 2", "multipart unit must stay contiguous and ordered"
    print("✓ Multipart contiguity in block test passed")


def test_duration_budget():
    show_units = {s: _units_for(s, 50) for s in ("a", "b", "c", "d")}
    target = 4 * 3600 * 1000
    max_ms = 5 * 3600 * 1000
    episodes, _ = assemble_block(show_units, {}, target_ms=target, max_ms=max_ms)
    total = sum(e["duration_ms"] for e in episodes)
    assert target <= total <= max_ms, f"total {total} outside [{target}, {max_ms}]"
    print("✓ Duration budget test passed")


def test_none_duration_uses_default():
    eps = [ep("a", 1, i + 1, f"Ep {i + 1}", duration_ms=None) for i in range(30)]
    show_units = {"a": detect_multipart_groups(eps), "b": _units_for("b", 30)}
    episodes, _ = assemble_block(show_units, {}, target_ms=60 * 60 * 1000,
                                 max_ms=2 * 3600 * 1000)
    assert episodes, "None durations should budget at the default, not break assembly"
    assert any(e["duration_ms"] is None for e in episodes)
    print("✓ None-duration default budgeting test passed")


def test_single_show_terminates():
    show_units = {"a": _units_for("a", 100)}
    episodes, _ = assemble_block(show_units, {}, target_ms=4 * 3600 * 1000,
                                 max_ms=5 * 3600 * 1000)
    assert len(episodes) <= 1, "a lone show cannot fill a block without adjacency"
    print("✓ Single-show termination test passed")


def test_empty_input():
    episodes, consumption = assemble_block({}, {}, target_ms=1000, max_ms=2000)
    assert episodes == [] and consumption == {}
    print("✓ Empty input test passed")


def test_cursor_start_position():
    show_units = {"a": _units_for("a", 10), "b": _units_for("b", 10)}
    episodes, consumption = assemble_block(
        show_units, {"a": 3, "b": 0},
        target_ms=44 * 60 * 1000, max_ms=2 * 3600 * 1000)
    a_eps = [e for e in episodes if e["show_key"] == "a"]
    assert a_eps[0]["episode"] == 4, "show 'a' should start at its cursor (index 3)"
    assert consumption["a"]["next_index"] > 3
    print("✓ Cursor start position test passed")


def test_recent_keys_skipped():
    show_units = {"a": _units_for("a", 10), "b": _units_for("b", 10)}
    recent = ["a-s1e1", "a-s1e2"]
    episodes, _ = assemble_block(show_units, {}, target_ms=44 * 60 * 1000,
                                 max_ms=2 * 3600 * 1000, recent_keys=recent)
    a_keys = [e["key"] for e in episodes if e["show_key"] == "a"]
    assert "a-s1e1" not in a_keys and "a-s1e2" not in a_keys
    print("✓ Recent episodes skipped test passed")


def test_preferred_keys_boost():
    eps_a = [ep("a", 1, i + 1, f"Episode {i + 1}") for i in range(10)]
    eps_a[6]["title"] = "Halloween Spooktacular"
    show_units = {"a": detect_multipart_groups(eps_a), "b": _units_for("b", 10)}
    preferred = {eps_a[6]["key"]}
    episodes, _ = assemble_block(show_units, {}, target_ms=44 * 60 * 1000,
                                 max_ms=2 * 3600 * 1000, preferred_keys=preferred)
    a_eps = [e for e in episodes if e["show_key"] == "a"]
    assert a_eps[0]["title"] == "Halloween Spooktacular", \
        f"preferred episode should play first, got {a_eps[0]['title']}"
    print("✓ Preferred keys boost test passed")


def test_preferred_respects_recent():
    eps_a = [ep("a", 1, i + 1, f"Episode {i + 1}") for i in range(5)]
    show_units = {"a": detect_multipart_groups(eps_a), "b": _units_for("b", 5)}
    preferred = {eps_a[2]["key"]}
    recent = {eps_a[2]["key"]}
    episodes, _ = assemble_block(show_units, {}, target_ms=44 * 60 * 1000,
                                 max_ms=2 * 3600 * 1000,
                                 recent_keys=recent, preferred_keys=preferred)
    a_eps = [e for e in episodes if e["show_key"] == "a"]
    assert a_eps and a_eps[0]["key"] != eps_a[2]["key"], \
        "recently played episodes must not be boosted"
    print("✓ Preferred-vs-recent precedence test passed")


def test_select_shows_rotation():
    candidates = [{"key": k, "title": k} for k in ("a", "b", "c", "d")]
    history = {
        "last_block_shows": ["a", "b"],
        "shows": {
            "a": {"last_used": "2026-10-04", "times_used": 3},
            "b": {"last_used": "2026-10-04", "times_used": 1},
            "c": {"last_used": "2026-09-01", "times_used": 5},
        },
    }
    selected = select_shows_for_block(candidates, history, 2)
    keys = {c["key"] for c in selected}
    assert keys == {"c", "d"}, f"should rotate away from last block, got {keys}"
    print("✓ Show rotation selection test passed")


def run_all_tests():
    print("\nRunning blocks tests...")
    print("=" * 50)
    tests = [
        test_multipart_part_n,
        test_multipart_trailing_number,
        test_multipart_word_numbers,
        test_no_false_positive_similar_words,
        test_no_group_different_prefix,
        test_no_group_non_consecutive,
        test_season_boundary_multipart,
        test_no_adjacent_same_show,
        test_multipart_adjacency_allowed_and_ordered,
        test_duration_budget,
        test_none_duration_uses_default,
        test_single_show_terminates,
        test_empty_input,
        test_cursor_start_position,
        test_recent_keys_skipped,
        test_preferred_keys_boost,
        test_preferred_respects_recent,
        test_select_shows_rotation,
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
        print(f"✓ All {len(tests)} blocks tests passed!")
        return True
    print(f"✗ {failed}/{len(tests)} tests failed")
    return False


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
