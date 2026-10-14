#!/usr/bin/env python3
import sys
import os

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.blocks import filter_show_candidates


def rec(title, genres, episodes=50, seasons=4):
    return {"key": title, "title": title, "genres": genres,
            "episode_count": episodes, "season_count": seasons}

SHOWS = [
    rec("SpongeBob", ["Animation", "Comedy", "Children"]),
    rec("Trailer Park Boys", ["Comedy"]),
    rec("The Office", ["Comedy"]),
    rec("Band of Brothers", ["Drama", "War"], episodes=10, seasons=1),
    rec("Planet Earth", ["Documentary"], episodes=11, seasons=1),
    rec("Breaking Bad", ["Drama", "Crime"], episodes=62, seasons=5),
]


def titles(records):
    return [r["title"] for r in records]


def test_exclude_genres():
    out = filter_show_candidates(SHOWS, genre_hints=["Comedy"],
                                 exclude_genres=["Animation", "Children"],
                                 min_needed=1)
    assert titles(out) == ["Trailer Park Boys", "The Office"], f"got {titles(out)}"
    print("✓ Exclude genres test passed")


def test_exclude_single_season():
    out = filter_show_candidates(SHOWS, exclude_single_season=True)
    assert "Band of Brothers" not in titles(out)
    assert "Planet Earth" not in titles(out)
    assert "Breaking Bad" in titles(out)
    print("✓ Exclude single-season test passed")


def test_min_episodes():
    out = filter_show_candidates(SHOWS, min_episodes=12)
    assert "Band of Brothers" not in titles(out)
    assert "Planet Earth" not in titles(out)
    assert "The Office" in titles(out)
    print("✓ Min episodes test passed")


def test_genre_hint_fallback():
    # include-filter leaves fewer than min_needed -> keep all shows
    out = filter_show_candidates(SHOWS, genre_hints=["Western"], min_needed=2)
    assert len(out) == len(SHOWS), f"got {len(out)}"
    print("✓ Genre hint fallback test passed")


def test_exclusions_are_hard_even_after_fallback():
    # include fallback keeps all, but exclusions still apply
    out = filter_show_candidates(SHOWS, genre_hints=["Western"],
                                 exclude_genres=["Animation"], min_needed=2)
    assert "SpongeBob" not in titles(out)
    assert len(out) == len(SHOWS) - 1
    print("✓ Hard exclusion after fallback test passed")


def test_no_filters_passthrough():
    out = filter_show_candidates(SHOWS)
    assert out == SHOWS
    print("✓ No-filter passthrough test passed")


def run_all_tests():
    print("\nRunning show-filter tests...")
    print("=" * 50)
    tests = [
        test_exclude_genres,
        test_exclude_single_season,
        test_min_episodes,
        test_genre_hint_fallback,
        test_exclusions_are_hard_even_after_fallback,
        test_no_filters_passthrough,
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
        print(f"✓ All {len(tests)} show-filter tests passed!")
        return True
    print(f"✗ {failed}/{len(tests)} tests failed")
    return False


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
