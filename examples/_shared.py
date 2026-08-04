"""Shared helpers for the examples.

Loads ``examples/.env`` if ``python-dotenv`` is available (optional), and reads
the Drupal connection settings from the environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:  # optional convenience — examples work without it if you export vars
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:  # pragma: no cover - examples only
    pass


def base_url() -> str:
    """Return DRUPAL_BASE_URL or exit with a helpful message."""
    url = os.environ.get("DRUPAL_BASE_URL")
    if not url:
        sys.exit(
            "Set DRUPAL_BASE_URL (see examples/.env.example). "
            "e.g. export DRUPAL_BASE_URL=https://drupal.ddev.site"
        )
    return url


def credentials() -> tuple[str, str]:
    """Return (username, password) or exit with a helpful message."""
    user = os.environ.get("DRUPAL_USERNAME")
    password = os.environ.get("DRUPAL_PASSWORD")
    if not user or not password:
        sys.exit(
            "Set DRUPAL_USERNAME and DRUPAL_PASSWORD (see examples/.env.example)."
        )
    return user, password
