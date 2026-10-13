#!/usr/bin/env python3
import sys
import os

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.tmdb import build_discover_params


def test_origin_country():
    params = build_discover_params({"origin_country": "ca"})
    assert params == {"with_origin_country": "CA"}, f"got {params}"
    print("✓ Origin country test passed")


def test_language():
    params = build_discover_params({"language": "FR"})
    assert params == {"with_original_language": "fr"}, f"got {params}"
    print("✓ Language test passed")


def test_genres_names_to_ids():
    params = build_discover_params({"genres": ["War", "History"]})
    assert params == {"with_genres": "10752|36"}, f"got {params}"
    print("✓ Genre name mapping test passed")


def test_genres_comma_string():
    params = build_discover_params({"genres": "Sci-Fi, Horror"})
    assert params == {"with_genres": "878|27"}, f"got {params}"
    print("✓ Genre comma-string test passed")


def test_unknown_genre_ignored():
    params = build_discover_params({"genres": ["War", "Notagenre"]})
    assert params == {"with_genres": "10752"}, f"got {params}"
    print("✓ Unknown genre ignored test passed")


def test_numeric_genre_passthrough():
    params = build_discover_params({"genres": ["10752"]})
    assert params == {"with_genres": "10752"}, f"got {params}"
    print("✓ Numeric genre id test passed")


def test_year_range():
    params = build_discover_params({"year_from": 1970, "year_to": 1999})
    assert params == {"primary_release_date.gte": "1970-01-01",
                      "primary_release_date.lte": "1999-12-31"}, f"got {params}"
    print("✓ Year range test passed")


def test_min_votes():
    params = build_discover_params({"min_votes": "100"})
    assert params == {"vote_count.gte": 100}, f"got {params}"
    print("✓ Min votes test passed")


def test_raw_keys_passthrough():
    params = build_discover_params({"with_origin_country": "CA",
                                    "vote_count.gte": 50})
    assert params == {"with_origin_country": "CA", "vote_count.gte": 50}, f"got {params}"
    print("✓ Raw TMDB key passthrough test passed")


def test_combined():
    params = build_discover_params({"origin_country": "CA", "language": "fr",
                                    "genres": ["Comedy"], "year_from": 2000})
    assert params == {"with_origin_country": "CA",
                      "with_original_language": "fr",
                      "with_genres": "35",
                      "primary_release_date.gte": "2000-01-01"}, f"got {params}"
    print("✓ Combined filters test passed")


def test_empty():
    assert build_discover_params({}) == {}
    assert build_discover_params(None) == {}
    print("✓ Empty input test passed")


def run_all_tests():
    print("\nRunning TMDB discover-params tests...")
    print("=" * 50)
    tests = [
        test_origin_country,
        test_language,
        test_genres_names_to_ids,
        test_genres_comma_string,
        test_unknown_genre_ignored,
        test_numeric_genre_passthrough,
        test_year_range,
        test_min_votes,
        test_raw_keys_passthrough,
        test_combined,
        test_empty,
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
        print(f"✓ All {len(tests)} discover tests passed!")
        return True
    print(f"✗ {failed}/{len(tests)} tests failed")
    return False


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
