"""Root conftest.py — ensures tests can import production modules.

The production code lives in guardian/, courier/, router/, bin/.
Tests import using the original module names:
  - soul_courier.* (package imports)
  - soul-guardian   (importlib.import_module with hyphen)
  - soul-router     (importlib.import_module with hyphen)
  - soul-msg        (extensionless script via importlib.util)

This conftest adds the repo root to sys.path so that the symlinks
(soul_courier -> courier, soul-guardian.py -> guardian/guardian.py, etc.)
are found by importlib and direct imports.
"""
import sys
from pathlib import Path

# Ensure repo root is on sys.path for all test sessions
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
