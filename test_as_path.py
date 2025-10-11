#!/usr/bin/env python3
"""Test AS_PATH parsing with both 2-byte and 4-byte AS numbers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pybmpmon.protocol.bgp_parser import parse_as_path

# Test 1: 4-byte AS numbers (from your BMP message)
# Segment type: 0x02 (AS_SEQUENCE)
# Segment length: 0x03 (3 AS numbers)
# AS numbers: 3356, 15169, 36492
test_4byte = bytes.fromhex("02 03 00 00 0d 1c 00 00 3b 41 00 00 8e 8c".replace(" ", ""))
print("Test 1: 4-byte AS numbers")
print(f"Input: {test_4byte.hex()}")
result = parse_as_path(test_4byte)
print(f"Result: {result}")
print(f"Expected: [3356, 15169, 36492]")
print(f"✓ PASS" if result == [3356, 15169, 36492] else "✗ FAIL")
print()

# Test 2: 2-byte AS numbers (legacy format)
# Segment type: 0x02 (AS_SEQUENCE)
# Segment length: 0x03 (3 AS numbers)
# AS numbers: 100, 200, 300
test_2byte = bytes.fromhex("02 03 00 64 00 c8 01 2c")
print("Test 2: 2-byte AS numbers (legacy)")
print(f"Input: {test_2byte.hex()}")
result = parse_as_path(test_2byte)
print(f"Result: {result}")
print(f"Expected: [100, 200, 300]")
print(f"✓ PASS" if result == [100, 200, 300] else "✗ FAIL")
print()

# Test 3: Empty AS_PATH
test_empty = bytes.fromhex("")
print("Test 3: Empty AS_PATH")
print(f"Input: (empty)")
result = parse_as_path(test_empty)
print(f"Result: {result}")
print(f"Expected: []")
print(f"✓ PASS" if result == [] else "✗ FAIL")
print()

# Test 4: Single 4-byte AS number
test_single = bytes.fromhex("02 01 00 00 0d 1c")
print("Test 4: Single 4-byte AS number")
print(f"Input: {test_single.hex()}")
result = parse_as_path(test_single)
print(f"Result: {result}")
print(f"Expected: [3356]")
print(f"✓ PASS" if result == [3356] else "✗ FAIL")
print()

# Test 5: Multiple segments with 4-byte AS numbers
test_multi = bytes.fromhex("02 02 00 00 0d 1c 00 00 3b 41 01 01 00 00 8e 8c")
print("Test 5: Multiple segments (AS_SEQUENCE + AS_SET) with 4-byte AS numbers")
print(f"Input: {test_multi.hex()}")
result = parse_as_path(test_multi)
print(f"Result: {result}")
print(f"Expected: [3356, 15169, 36492]")
print(f"✓ PASS" if result == [3356, 15169, 36492] else "✗ FAIL")

print("\nAll tests completed!")
