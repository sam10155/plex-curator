#!/usr/bin/env python3
import sys
import os

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.utils import clean_keywords

def test_basic_cleaning():
    """Test basic keyword cleaning without artifacts."""
    keywords = ["Christmas", "Holiday", "Family", "Winter"]
    result = clean_keywords(keywords)
    assert result == ["Christmas", "Holiday", "Family", "Winter"]
    print("✓ Basic cleaning test passed")

def test_json_artifact_removal():
    """Test removal of JSON artifacts."""
    keywords = ['Genre":', '["Christmas"]', 'Holiday', '"Family"', 'Winter']
    result = clean_keywords(keywords)
    assert "Christmas" in result
    assert "Holiday" in result
    assert "Family" in result
    assert "Winter" in result
    assert 'Genre":' not in result
    assert '["Christmas"]' not in result
    print("✓ JSON artifact removal test passed")

def test_leading_numbers():
    """Test stripping of leading numbers."""
    keywords = ["1. Christmas", "2. Holiday", "3. Family"]
    result = clean_keywords(keywords)
    assert "Christmas" in result
    assert "Holiday" in result
    assert "Family" in result
    assert "1. Christmas" not in result
    print("✓ Leading numbers test passed")

def test_min_length_filter():
    """Test minimum length filtering (3 chars)."""
    keywords = ["A", "AB", "ABC", "Christmas"]
    result = clean_keywords(keywords)
    assert "A" not in result
    assert "AB" not in result
    assert "ABC" in result
    assert "Christmas" in result
    print("✓ Min length filter test passed")

def test_special_character_filter():
    """Test that keywords with special characters are filtered out."""
    keywords = ["Christmas", "Holiday!", "Family@Home", "Winter-Time", "Joy"]
    result = clean_keywords(keywords)
    assert "Christmas" in result
    assert "Winter-Time" in result
    assert "Joy" in result
    assert "Holiday!" not in result
    assert "Family@Home" not in result
    print("✓ Special character filter test passed")

def test_empty_and_whitespace():
    """Test handling of empty strings and whitespace."""
    keywords = ["Christmas", "", "  ", "Holiday", None, "Family"]
    keywords = [k for k in keywords if k is not None]
    result = clean_keywords(keywords)
    assert "Christmas" in result
    assert "Holiday" in result
    assert "Family" in result
    assert "" not in result
    assert "  " not in result
    print("✓ Empty and whitespace test passed")

def test_malformed_ai_response():
    """Test the actual malformed response case from production."""
    keywords = ['Genre": ["Christmas', '"Holiday"', 'Seasonal"', 'Theme": ["Family', 'Love']
    result = clean_keywords(keywords)
    assert "Christmas" in result or "Holiday" in result or "Seasonal" in result
    assert "Family" in result or "Love" in result
    assert len(result) >= 2
    print("✓ Malformed AI response test passed")

def test_mixed_case():
    """Test that keywords preserve case."""
    keywords = ["Christmas", "HOLIDAY", "fAmIlY"]
    result = clean_keywords(keywords)
    assert "Christmas" in result
    assert "HOLIDAY" in result
    assert "fAmIlY" in result
    print("✓ Mixed case test passed")

def test_numbers_in_keywords():
    """Test that keywords with numbers (not at start) are allowed."""
    keywords = ["Christmas2024", "Holiday", "Top10"]
    result = clean_keywords(keywords)
    assert "Christmas2024" in result
    assert "Holiday" in result
    assert "Top10" in result
    print("✓ Numbers in keywords test passed")

def test_must_start_with_letter():
    """Test that keywords must start with a letter."""
    keywords = ["Christmas", "1Holiday", "-Family", "Winter"]
    result = clean_keywords(keywords)
    assert "Christmas" in result
    assert "Winter" in result
    assert "1Holiday" not in result
    assert "-Family" not in result
    print("✓ Must start with letter test passed")

def run_all_tests():
    """Run all utils tests."""
    print("\nRunning utils tests...")
    print("=" * 50)
    
    tests = [
        test_basic_cleaning,
        test_json_artifact_removal,
        test_leading_numbers,
        test_min_length_filter,
        test_special_character_filter,
        test_empty_and_whitespace,
        test_malformed_ai_response,
        test_mixed_case,
        test_numbers_in_keywords,
        test_must_start_with_letter
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
        print(f"✓ All {len(tests)} utils tests passed!")
        return True
    else:
        print(f"✗ {failed}/{len(tests)} tests failed")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
