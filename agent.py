"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card, compare_listing


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "price_comparison": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "fallback_adjusted": None,
        "error": None,
    }


# ── query parsing ─────────────────────────────────────────────────────────────

_PRICE_PHRASE_RE = re.compile(
    r"(?:under|below|less than|no more than|at most|up to|max(?:imum)?|<=?)\s*\$?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_PRICE_BARE_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
_SIZE_RE = re.compile(
    r"\b(?:in\s+)?size\s*[:\-]?\s*([A-Za-z0-9/]+)\b",
    re.IGNORECASE,
)


def _parse_query(query: str) -> dict:
    """Extract description, size, and max_price from a free-text query."""
    text = query or ""

    max_price = None
    m = _PRICE_PHRASE_RE.search(text)
    if m:
        max_price = float(m.group(1))
        text = text[: m.start()] + " " + text[m.end():]
    else:
        m = _PRICE_BARE_RE.search(text)
        if m:
            max_price = float(m.group(1))
            text = text[: m.start()] + " " + text[m.end():]

    size = None
    m = _SIZE_RE.search(text)
    if m:
        size = m.group(1)
        text = text[: m.start()] + " " + text[m.end():]

    description = re.sub(r"\s+", " ", text).strip(" ,.;:!?")

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Run the FitFindr planning loop for a single user interaction.

    The loop branches on what search_listings returns:
      * empty → broaden the search; if still empty, set session["error"]
                and return early WITHOUT calling suggest_outfit / create_fit_card.
      * non-empty → pick the top item, call suggest_outfit, then create_fit_card.

    Args:
        query:    Natural language user request.
        wardrobe: Wardrobe dict with an "items" list (may be empty).

    Returns:
        The session dict. If session["error"] is not None the run halted early
        and outfit_suggestion / fit_card will be None.
    """
    # Step 1: initialize session state
    session = _new_session(query, wardrobe)

    # Step 2: parse query into structured params
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: primary search
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )

    # Step 4: branch — empty results trigger a broadened retry, then error
    if not results:
        broadened_price = (
            round(parsed["max_price"] * 1.25, 2) if parsed["max_price"] else None
        )
        bits = ["removed size filter"] if parsed["size"] else []
        if broadened_price and parsed["max_price"]:
            bits.append(f"raised price ceiling to ${broadened_price:.2f}")
        session["fallback_adjusted"] = (
            "No exact matches — broadened search (" + "; ".join(bits) + ")."
            if bits
            else "No exact matches — retrying with relaxed constraints."
        )

        results = search_listings(
            description=parsed["description"],
            size=None,
            max_price=broadened_price,
        )

        if not results:
            session["error"] = (
                "No matching listings found, even after broadening the search. "
                "Try different keywords or adjust your filters."
            )
            return session

    # Step 5: store full results + pick the top-ranked item
    session["search_results"] = results
    session["selected_item"] = results[0]

    # Step 6: price comparison against comparable listings
    session["price_comparison"] = compare_listing(session["selected_item"])

    # Step 7: outfit suggestion uses the selected item + wardrobe
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit

    # Step 8: fit card uses the outfit text + selected item
    session["fit_card"] = create_fit_card(outfit, session["selected_item"])

    # Step 9: return the fully populated session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Parsed: {session['parsed']}")
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nselected_item dict passed into suggest_outfit:")
        print(f"  id={session['selected_item']['id']}  price=${session['selected_item']['price']}")
        print(f"\nPrice comparison: {session['price_comparison']}")
        print(f"\nOutfit (this exact string went into create_fit_card):")
        print(session['outfit_suggestion'])
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Parsed: {session2['parsed']}")
    print(f"Fallback note: {session2['fallback_adjusted']}")
    print(f"Error message: {session2['error']}")
    print(f"selected_item: {session2['selected_item']}")
    print(f"outfit_suggestion: {session2['outfit_suggestion']}")
    print(f"fit_card: {session2['fit_card']}")
    assert session2["fit_card"] is None, "fit_card must be None on the no-results branch"
    assert session2["error"] is not None, "error must be set on the no-results branch"
    print("\nBranching verified: suggest_outfit/create_fit_card were NOT called.")
