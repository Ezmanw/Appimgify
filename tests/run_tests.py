#!/usr/bin/env python3
"""Run the whole unit-test suite.

Used both by ``meson test`` and directly during development::

    python3 tests/run_tests.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = TESTS_ROOT.parent / "src"

for path in (str(TESTS_ROOT), str(SOURCE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(TESTS_ROOT), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2, buffer=False)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
