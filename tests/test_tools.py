"""Tests for the three required FitFindr tools.

Each tool has at least one test per failure mode described in planning.md.
Run with:  pytest tests/
"""

import os
import sys

import pytest

# Make the project root importable when pytest is invoked from anywhere.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tools import create_fit_card, search_listings, suggest_outfit  # noqa: E402
from utils.data_loader import get_example_wardrobe  # noqa: E402


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Nothing in the mock dataset matches a designer ballgown under $5 in XXS.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_case_insensitive():
    results = search_listings("tee", size="m", max_price=100)
    # Every returned item must have a size string that mentions M / medium.
    for item in results:
        sz = item["size"].lower()
        assert ("m" in sz) or ("medium" in sz)


# ── suggest_outfit ────────────────────────────────────────────────────────────

_HAS_GROQ_KEY = bool(os.environ.get("GROQ_API_KEY"))
_skip_no_key = pytest.mark.skipif(
    not _HAS_GROQ_KEY,
    reason="GROQ_API_KEY not set — skipping LLM-backed test.",
)

_SAMPLE_ITEM = {
    "id": "lst_999",
    "title": "Faded Band Tee",
    "description": "Soft worn-in vintage band tee with a faded graphic.",
    "category": "tops",
    "style_tags": ["vintage", "graphic tee", "grunge"],
    "size": "M",
    "condition": "good",
    "price": 22.00,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}


@_skip_no_key
def test_suggest_outfit_with_empty_wardrobe():
    """Empty wardrobe should fall back to general styling advice, not crash."""
    out = suggest_outfit(_SAMPLE_ITEM, {"items": []})
    assert isinstance(out, str)
    assert out.strip() != ""


@_skip_no_key
def test_suggest_outfit_with_populated_wardrobe():
    wardrobe = get_example_wardrobe()
    out = suggest_outfit(_SAMPLE_ITEM, wardrobe)
    assert isinstance(out, str)
    assert len(out.strip()) > 20


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    """Empty outfit must return a descriptive error string — not raise."""
    result = create_fit_card("", _SAMPLE_ITEM)
    assert isinstance(result, str)
    assert "error" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    result = create_fit_card("   \n  ", _SAMPLE_ITEM)
    assert isinstance(result, str)
    assert "error" in result.lower()


@_skip_no_key
def test_create_fit_card_returns_caption():
    outfit = (
        "Pair the band tee with baggy dark-wash jeans and chunky white sneakers. "
        "Layer a cropped black denim jacket over the top for a classic 90s grunge feel."
    )
    caption = create_fit_card(outfit, _SAMPLE_ITEM)
    assert isinstance(caption, str)
    assert len(caption.strip()) > 0
    assert "error" not in caption.lower()[:30]
