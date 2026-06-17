"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


_GROQ_MODEL = "llama-3.3-70b-versatile"

_SIZE_ALIASES = {
    "xs": {"xs", "extra small", "extra-small"},
    "s": {"s", "small", "sm"},
    "m": {"m", "medium", "med"},
    "l": {"l", "large", "lg"},
    "xl": {"xl", "extra large", "extra-large"},
    "xxl": {"xxl", "2xl", "extra extra large"},
}

_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "of", "in", "on", "to", "with",
    "i", "im", "i'm", "is", "are", "was", "were", "be", "been", "being",
    "looking", "want", "need", "find", "some", "any", "my", "me", "you",
    "this", "that", "these", "those", "it", "its", "at", "from", "by",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _tokenize(text: str) -> list[str]:
    """Lowercase + split on non-alphanumerics; drop stopwords and 1-char tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _normalize_size(size: str) -> set[str]:
    """Return the set of canonical tokens that represent this size."""
    s = size.strip().lower()
    if not s:
        return set()
    for canonical, aliases in _SIZE_ALIASES.items():
        if s in aliases:
            return {canonical} | aliases
    return {s}


def _size_matches(query_size: str, listing_size: str) -> bool:
    """Case-insensitive partial size match (e.g., 'S' matches 'S/M', 'medium' matches 'M')."""
    if not query_size:
        return True
    listing_lower = (listing_size or "").lower()
    if not listing_lower:
        return False
    query_tokens = _normalize_size(query_size)
    listing_tokens = re.findall(r"[a-z0-9]+", listing_lower)
    listing_set = set(listing_tokens) | {listing_lower}
    for qt in query_tokens:
        if qt in listing_set:
            return True
        for lt in listing_tokens:
            if qt == lt:
                return True
    if query_size.strip().lower() in listing_lower:
        return True
    return False


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()
    query_tokens = _tokenize(description or "")

    scored: list[tuple[int, dict]] = []
    for item in listings:
        if max_price is not None and item.get("price", 0) > max_price:
            continue
        if size and not _size_matches(size, item.get("size", "")):
            continue

        haystack_parts = [
            item.get("title", ""),
            item.get("description", ""),
            item.get("category", ""),
            " ".join(item.get("style_tags", []) or []),
            " ".join(item.get("colors", []) or []),
            item.get("brand") or "",
        ]
        haystack = _tokenize(" ".join(haystack_parts))
        haystack_set = set(haystack)

        if not query_tokens:
            score = 1
        else:
            score = sum(1 for t in query_tokens if t in haystack_set)
            if score == 0:
                continue

        scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    client = _get_groq_client()

    item_title = new_item.get("title", "an unknown item")
    item_desc = new_item.get("description", "")
    item_category = new_item.get("category", "")
    item_tags = ", ".join(new_item.get("style_tags", []) or [])
    item_colors = ", ".join(new_item.get("colors", []) or [])

    items = (wardrobe or {}).get("items") or []

    if not items:
        prompt = (
            "You are a personal stylist. The user is considering buying this thrifted item "
            "but has not yet listed any items in their wardrobe.\n\n"
            f"Item: {item_title}\n"
            f"Category: {item_category}\n"
            f"Style tags: {item_tags}\n"
            f"Colors: {item_colors}\n"
            f"Description: {item_desc}\n\n"
            "Give 1–2 outfit ideas using generic staple pieces (e.g., 'a plain white tee', "
            "'high-rise straight-leg jeans'). Keep it concise (4–6 sentences). End with a brief "
            "note on the vibe the look gives off."
        )
    else:
        wardrobe_lines = []
        for w in items:
            name = w.get("name", "unnamed piece")
            cat = w.get("category", "")
            colors = ", ".join(w.get("colors", []) or [])
            tags = ", ".join(w.get("style_tags", []) or [])
            notes = w.get("notes") or ""
            wardrobe_lines.append(
                f"- {name} (category: {cat}; colors: {colors}; tags: {tags})"
                + (f" — notes: {notes}" if notes else "")
            )
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            "You are a personal stylist. Suggest 1–2 complete outfits that pair the new item "
            "with specific pieces from the user's wardrobe below. Reference the wardrobe pieces "
            "by name. Keep it concise (5–8 sentences total) and mention any styling tips "
            "(rolling sleeves, tucking, layering, etc.).\n\n"
            f"NEW ITEM:\n"
            f"  Title: {item_title}\n"
            f"  Category: {item_category}\n"
            f"  Style tags: {item_tags}\n"
            f"  Colors: {item_colors}\n"
            f"  Description: {item_desc}\n\n"
            f"USER'S WARDROBE:\n{wardrobe_text}\n"
        )

    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[
            {"role": "system", "content": "You are a concise, knowledgeable personal stylist."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


# ── Tool 4: compare_listing ───────────────────────────────────────────────────

def compare_listing(selected_item: dict) -> dict | None:
    """
    Compare the selected item's price against comparable listings in the dataset.

    Comparables are items in the same category, excluding the item itself.
    If at least two of those also share a style tag with the selected item,
    the comparison is narrowed to that tag-matched subset (tighter signal).

    Args:
        selected_item: The listing dict returned by search_listings.

    Returns:
        {
          "average_price":     float,  # rounded to 2 decimals
          "difference_percent": float, # negative = item is below average
          "deal_rating":       "Good Deal" | "Fair Price" | "Overpriced",
        }
        or None if comparison can't be done (missing fields, no comparables, etc.).
    """
    if not isinstance(selected_item, dict):
        return None

    price = selected_item.get("price")
    category = selected_item.get("category")
    if not isinstance(price, (int, float)) or not category:
        return None

    listings = load_listings()
    item_id = selected_item.get("id")
    item_tags = set(selected_item.get("style_tags") or [])

    same_category = [
        l for l in listings
        if l.get("category") == category
        and l.get("id") != item_id
        and isinstance(l.get("price"), (int, float))
    ]
    if not same_category:
        return None

    tag_matched = [l for l in same_category if item_tags & set(l.get("style_tags") or [])]
    comparables = tag_matched if len(tag_matched) >= 2 else same_category

    avg = sum(l["price"] for l in comparables) / len(comparables)
    if avg <= 0:
        return None

    diff_pct = ((price - avg) / avg) * 100.0
    if diff_pct <= -10:
        rating = "Good Deal"
    elif diff_pct <= 10:
        rating = "Fair Price"
    else:
        rating = "Overpriced"

    return {
        "average_price": round(avg, 2),
        "difference_percent": round(diff_pct, 1),
        "deal_rating": rating,
    }


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.
    """
    if not outfit or not str(outfit).strip():
        return (
            "Error: Could not generate a fit card due to missing styling information."
        )

    client = _get_groq_client()

    item_title = new_item.get("title", "this thrifted piece")
    item_price = new_item.get("price", "")
    item_platform = new_item.get("platform", "")
    price_str = f"${item_price:.2f}" if isinstance(item_price, (int, float)) else str(item_price)

    prompt = (
        "Write a single short Instagram/TikTok OOTD caption (2–4 sentences). It should:\n"
        "- Feel casual and authentic — like a real post, not a product description.\n"
        "- Mention the item name, price, and platform naturally (each only once).\n"
        "- Capture the outfit vibe in specific terms based on the styling notes.\n"
        "- Sound fresh and varied; avoid generic phrases like 'check out this look'.\n"
        "- May include 0–3 relevant hashtags at the end.\n\n"
        f"Item: {item_title}\n"
        f"Price: {price_str}\n"
        f"Platform: {item_platform}\n\n"
        f"Outfit / styling notes:\n{outfit}\n\n"
        "Return ONLY the caption text — no preamble, no quotes."
    )

    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[
            {"role": "system", "content": "You write punchy, authentic-sounding OOTD captions."},
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,
    )
    return response.choices[0].message.content.strip()
