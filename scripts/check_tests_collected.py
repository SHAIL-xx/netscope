"""Fail if a test method is defined but never collected by unittest."""
import glob
import re
import sys
import unittest

collected = unittest.defaultTestLoader.discover("tests").countTestCases()

defined = 0
for path in sorted(glob.glob("tests/test_*.py")):
    with open(path, encoding="utf-8") as f:
        defined += len(re.findall(r"^\s*def test_", f.read(), re.MULTILINE))

print(f"defined={defined} collected={collected}")
if defined != collected:
    print("ERROR: some test methods are defined but never run "
          "(duplicate name or wrong indentation?)")
    sys.exit(1)