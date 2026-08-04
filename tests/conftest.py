"""Shared pytest fixtures.

Provides ``load_fixture``, a loader for the JSON files under
``tests/fixtures/``.  Those files are copied **verbatim** from the JavaScript
source-of-truth client's golden corpus so that both clients are exercised
against byte-identical server payloads (see ``tests/fixtures/README.md``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load and parse a shared JSON fixture by file name.

    Parameters
    ----------
    name:
        File name relative to ``tests/fixtures/`` (e.g. ``"node-recipe.json"``).
    """
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def fixture() -> Callable[[str], Any]:
    """Return the :func:`load_fixture` loader for use in tests."""
    return load_fixture
