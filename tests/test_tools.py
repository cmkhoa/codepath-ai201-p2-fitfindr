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

from tools import compare_listing, create_fit_card, search_listings, suggest_outfit  # noqa: E402
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


# ── compare_listing ───────────────────────────────────────────────────────────

def _item(price: float, category: str = "tops", tags=None, item_id: str = "lst_test") -> dict:
    """Build a minimal listing-shaped dict for compare_listing tests."""
    return {
        "id": item_id,
        "title": "Test Item",
        "category": category,
        "style_tags": tags if tags is not None else ["vintage", "graphic tee"],
        "price": price,
    }


def test_compare_listing_returns_expected_keys():
    """Standard input: returns a dict with the three documented keys."""
    result = compare_listing(_item(price=22.0))
    assert isinstance(result, dict)
    assert set(result.keys()) == {"average_price", "difference_percent", "deal_rating"}
    assert isinstance(result["average_price"], float)
    assert isinstance(result["difference_percent"], float)
    assert result["deal_rating"] in {"Good Deal", "Fair Price", "Overpriced"}


def test_compare_listing_good_deal_when_well_below_average():
    """A tops item at $10 sits ~50% below the ~$22 tops avg → Good Deal."""
    result = compare_listing(_item(price=10.0, category="tops"))
    assert result is not None
    assert result["deal_rating"] == "Good Deal"
    assert result["difference_percent"] < -10


def test_compare_listing_overpriced_when_well_above_average():
    """A tops item at $80 sits well above the ~$22 tops avg → Overpriced."""
    result = compare_listing(_item(price=80.0, category="tops"))
    assert result is not None
    assert result["deal_rating"] == "Overpriced"
    assert result["difference_percent"] > 10


def test_compare_listing_fair_price_near_average():
    """An outerwear item at $44 sits at the ~$44 outerwear avg → Fair Price."""
    result = compare_listing(
        _item(price=44.0, category="outerwear", tags=["vintage"])
    )
    assert result is not None
    assert result["deal_rating"] == "Fair Price"
    assert -10 <= result["difference_percent"] <= 10


def test_compare_listing_excludes_the_item_itself():
    """If the input matches a real listing's id, that listing must be excluded
    from the average so the item can't be its own comparable."""
    # lst_002 is the Y2K Baby Tee at $18 in tops — re-priced to $5 here.
    re_priced = _item(price=5.0, category="tops", item_id="lst_002")
    result = compare_listing(re_priced)
    assert result is not None
    # The real lst_002 ($18) must NOT be averaged in: 5 is FAR below tops avg → Good Deal.
    assert result["deal_rating"] == "Good Deal"


def test_compare_listing_none_input_returns_none():
    assert compare_listing(None) is None


def test_compare_listing_non_dict_input_returns_none():
    assert compare_listing("not a dict") is None
    assert compare_listing(123) is None


def test_compare_listing_missing_price_returns_none():
    assert compare_listing({"category": "tops"}) is None


def test_compare_listing_missing_category_returns_none():
    assert compare_listing({"price": 25.0}) is None


def test_compare_listing_invalid_price_type_returns_none():
    assert compare_listing(_item(price="cheap")) is None  # type: ignore[arg-type]


def test_compare_listing_unknown_category_returns_none():
    """A category that doesn't appear in the dataset has no comparables → None."""
    result = compare_listing(_item(price=20.0, category="not_a_real_category"))
    assert result is None


def test_compare_listing_difference_percent_sign_matches_price():
    """Sanity check: difference_percent is negative when the item is below avg
    and positive when above — same direction as price minus average."""
    low = compare_listing(_item(price=10.0, category="tops"))
    high = compare_listing(_item(price=80.0, category="tops"))
    assert low is not None and high is not None
    assert low["difference_percent"] < 0
    assert high["difference_percent"] > 0
