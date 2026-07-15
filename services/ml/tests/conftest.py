"""Test fixtures. Ensures the `app` package is importable and DB tests skip
cleanly when no database is configured."""
import os
import sys
from pathlib import Path

import pytest

# Make `import app...` work when pytest is run from services/ml or elsewhere.
_ML_ROOT = Path(__file__).resolve().parents[1]
if str(_ML_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_ROOT))

from app.config import get_settings  # noqa: E402


def has_db() -> bool:
    return bool(get_settings().database_url)


requires_db = pytest.mark.skipif(not has_db(), reason="DATABASE_URL not configured")
