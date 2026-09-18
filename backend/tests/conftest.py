import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("SCHEDULER_ENABLED", "false")

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture():
    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")
    return _load
