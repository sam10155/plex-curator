#!/usr/bin/env python3
import sys
import os

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.ai import match_verification_response

TITLES = ["Bon Cop Bad Cop", "Goon", "The Rocket", "Top Gun", "One Week"]


def test_numeric_indices():
    kept = match_verification_response(["1", "3", "5"], TITLES)
    assert kept == {0, 2, 4}, f"got {kept}"
    print("✓ Numeric indices test passed")


def test_int_indices():
    kept = match_verification_response([1, 2], TITLES)
    assert kept == {0, 1}, f"got {kept}"
    print("✓ Integer indices test passed")


def test_title_matching():
    kept = match_verification_response(["Goon", "One Week"], TITLES)
    assert kept == {1, 4}, f"got {kept}"
    print("✓ Title matching test passed")


def test_numbered_title_lines():
    kept = match_verification_response(["2. Goon", "3) The Rocket"], TITLES)
    assert kept == {1, 2}, f"got {kept}"
    print("✓ Numbered title lines test passed")


def test_title_with_year():
    kept = match_verification_response(["The Rocket (2005)"], TITLES)
    assert kept == {2}, f"got {kept}"
    print("✓ Title with year test passed")


def test_junk_ignored():
    kept = match_verification_response(
        ["99", "0", "Not A Real Movie", "Here are the movies that pass:"], TITLES)
    assert kept == set(), f"got {kept}"
    print("✓ Junk ignored test passed")


def test_numeric_title_not_confused():
    # a bare number is an index; a number starting a title is a title
    titles = ["12 Years a Slave", "Argo"]
    kept = match_verification_response(["12 Years a Slave", "2"], titles)
    assert kept == {0, 1}, f"got {kept}"
    print("✓ Numeric-prefix title test passed")


def run_all_tests():
    print("\nRunning requirement-verification tests...")
    print("=" * 50)
    tests = [
        test_numeric_indices,
        test_int_indices,
        test_title_matching,
        test_numbered_title_lines,
        test_title_with_year,
        test_junk_ignored,
        test_numeric_title_not_confused,
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
        print(f"✓ All {len(tests)} verification tests passed!")
        return True
    print(f"✗ {failed}/{len(tests)} tests failed")
    return False


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
