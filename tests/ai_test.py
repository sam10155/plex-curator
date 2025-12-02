#!/usr/bin/env python3
import sys
import os

if not os.path.exists("/opt/plex-curator/src"):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from core.ai import parse_ollama_response

def test_valid_json_array():
    """Test parsing a valid JSON array."""
    response = '["Christmas", "Holiday", "Festive", "Family"]'
    result = parse_ollama_response(response)
    assert result == ["Christmas", "Holiday", "Festive", "Family"]
    print("✓ Valid JSON array test passed")

def test_valid_json_dict():
    """Test parsing a dict with Genre/Theme structure."""
    response = '{"Genre": ["Christmas", "Holiday"], "Theme": ["Family", "Love"]}'
    result = parse_ollama_response(response)
    expected = ["Christmas", "Holiday", "Family", "Love"]
    assert set(result) == set(expected)
    print("✓ Valid JSON dict test passed")

def test_malformed_json_with_labels():
    """Test parsing malformed JSON like the user's example."""
    response = 'Genre": ["Christmas", "Holiday", "Seasonal", "Traditional"], Theme": ["Love", "Family", "Joy"]'
    result = parse_ollama_response(response)
    expected_keywords = ["Christmas", "Holiday", "Seasonal", "Traditional", "Love", "Family", "Joy"]
    assert all(kw in result for kw in expected_keywords)
    print("✓ Malformed JSON with labels test passed")

def test_embedded_arrays():
    """Test extracting keywords from embedded arrays."""
    response = 'The AI suggests: ["Action", "Adventure", "Thriller"] for this genre.'
    result = parse_ollama_response(response)
    assert "Action" in result
    assert "Adventure" in result
    assert "Thriller" in result
    print("✓ Embedded arrays test passed")

def test_comma_separated_list():
    """Test comma-separated fallback."""
    response = "Christmas, Holiday, Winter, Festive, Family"
    result = parse_ollama_response(response)
    expected = ["Christmas", "Holiday", "Winter", "Festive", "Family"]
    assert set(result) == set(expected)
    print("✓ Comma-separated list test passed")

def test_line_separated_list():
    """Test newline-separated fallback."""
    response = "Christmas\nHoliday\nWinter\nFestive"
    result = parse_ollama_response(response)
    expected = ["Christmas", "Holiday", "Winter", "Festive"]
    assert set(result) == set(expected)
    print("✓ Line-separated list test passed")

def test_numbered_list():
    """Test numbered list (should strip numbers)."""
    response = "1. Christmas\n2. Holiday\n3. Winter"
    result = parse_ollama_response(response)
    assert "Christmas" in result
    assert "Holiday" in result
    assert "Winter" in result
    assert not any(kw.startswith("1.") for kw in result)
    print("✓ Numbered list test passed")

def test_empty_response():
    """Test empty response handling."""
    result = parse_ollama_response("")
    assert result == []
    print("✓ Empty response test passed")

def test_keyword_limit():
    """Test that we don't return more than 10 keywords from arrays (malformed JSON path only)."""
    response = 'Genre": ["Word1", "Word2", "Word3", "Word4", "Word5", "Word6", "Word7", "Word8", "Word9", "Word10", "Word11", "Word12"]'
    result = parse_ollama_response(response)
    assert len(result) <= 10
    print("✓ Keyword limit test passed")

def test_min_length_filter():
    """Test that short keywords (<=2 chars) are filtered out in regex extraction path."""
    response = 'Keywords": ["A", "AB", "ABC", "Christmas"]'
    result = parse_ollama_response(response)
    assert "A" not in result
    assert "AB" not in result
    assert "ABC" in result
    assert "Christmas" in result
    print("✓ Min length filter test passed")

def run_all_tests():
    """Run all AI parsing tests."""
    print("\nRunning AI parsing tests...")
    print("=" * 50)
    
    tests = [
        test_valid_json_array,
        test_valid_json_dict,
        test_malformed_json_with_labels,
        test_embedded_arrays,
        test_comma_separated_list,
        test_line_separated_list,
        test_numbered_list,
        test_empty_response,
        test_keyword_limit,
        test_min_length_filter
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
        print(f"✓ All {len(tests)} AI parsing tests passed!")
        return True
    else:
        print(f"✗ {failed}/{len(tests)} tests failed")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
