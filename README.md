# FitFindr

FitFindr is an agent that takes a natural-language query for a secondhand clothing item, finds matching listings in a mock dataset, evaluates whether the top match is a good deal, suggests an outfit using the user's wardrobe, and writes a short shareable caption for the look.

## Setup

```bash
pip install -r requirements.txt
```

Add a `GROQ_API_KEY` to a `.env` file in the project root (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Run

```bash
python agent.py        # CLI demo: happy path + no-results branch
python app.py          # Gradio web UI on http://localhost:7860
pytest tests/          # 21 tests across all four tools
```

## Tool Inventory

| # | Tool | Inputs | Output | Purpose |
|---|---|---|---|---|
| 1 | `search_listings` | `description: str`, `size: str \| None`, `max_price: float \| None` | `list[dict]` — listings ranked by keyword-overlap score | Filter the mock dataset by price + size, then score by token overlap against title / description / category / tags / colors / brand. |
| 2 | `compare_listing` | `selected_item: dict` | `dict` with `average_price: float`, `difference_percent: float`, `deal_rating: str` — or `None` | Compute the average price of same-category listings (narrowed to tag-matched items when possible) and rate the selected item Good Deal / Fair Price / Overpriced. |
| 3 | `suggest_outfit` | `new_item: dict`, `wardrobe: dict` | `str` — outfit notes referencing specific wardrobe pieces | LLM-backed stylist that pairs the new item with named pieces from the user's wardrobe; falls back to generic staples when the wardrobe is empty. |
| 4 | `create_fit_card` | `outfit: str`, `new_item: dict` | `str` — 2–4 sentence OOTD caption (or descriptive error string) | LLM-backed caption writer that turns the outfit notes + listing details into a casual social-style post. |

Listing dicts always include `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform` — see [data/listings.json](data/listings.json).

## Planning Loop

The loop lives in `run_agent(query, wardrobe)` in [agent.py](agent.py). It does **not** call every tool unconditionally — what runs depends on what `search_listings` returns.

1. **Initialize.** `_new_session(query, wardrobe)` builds the session dict.
2. **Parse.** `_parse_query()` extracts `description`, `size`, `max_price` using regex (deterministic, no extra LLM hop) and stores them in `session["parsed"]`.
3. **Search.** Call `search_listings(description, size, max_price)`.
4. **Branch on the result:**
   - **Empty →** broaden constraints (drop the size filter, raise `max_price` by 25%), record what was changed in `session["fallback_adjusted"]`, and retry. If the second pass is also empty, set `session["error"]` and return the session early. `suggest_outfit` / `create_fit_card` / `compare_listing` are **not** called.
   - **Non-empty →** continue.
5. **Select.** Save the full ranked list to `session["search_results"]` and the top item to `session["selected_item"]`.
6. **Compare price.** `compare_listing(selected_item)` → `session["price_comparison"]`.
7. **Suggest outfit.** `suggest_outfit(selected_item, wardrobe)` → `session["outfit_suggestion"]`.
8. **Write fit card.** `create_fit_card(outfit_suggestion, selected_item)` → `session["fit_card"]`.
9. **Return** the populated session.

## State Management

A single session dict, created by `_new_session()`, is the only place data lives during a run. Every step reads its inputs from this dict and writes its output back to it; the next step reads from the dict rather than from a tool's return value directly.

**What is stored, when it's written, and how it flows to the next tool:**

| Field | Written at step | Read by |
|---|---|---|
| `query` | Step 1 (init) | parser at step 2 |
| `wardrobe` | Step 1 (init) | `suggest_outfit` at step 7 |
| `parsed` (description / size / max_price) | Step 2, after regex parse | `search_listings` at step 3 (and step 4's broadened retry) |
| `search_results` | Step 5, after a non-empty search | step 5's `selected_item = results[0]` |
| `selected_item` | Step 5, top of `search_results` | `compare_listing` (step 6), `suggest_outfit` (step 7), `create_fit_card` (step 8) |
| `price_comparison` | Step 6, after `compare_listing` | rendered by the UI / CLI |
| `outfit_suggestion` | Step 7, after `suggest_outfit` | `create_fit_card` at step 8 |
| `fit_card` | Step 8, after `create_fit_card` | rendered by the UI / CLI |
| `fallback_adjusted` | Step 4, if the primary search was empty | rendered as a note in the listing panel |
| `error` | Step 4, only if the broadened retry was also empty | causes the loop to return early; UI shows it in panel 1 |

This gives three guarantees the rubric calls out:

- **No re-entry.** The user query is parsed once into `session["parsed"]` and never re-read from the raw text. The `selected_item` dict that `compare_listing` sees is the same Python dict that `suggest_outfit` and `create_fit_card` see.
- **No hardcoded values between steps.** Each tool consumes whatever the previous tool stored — verified by inspection in the CLI demo (`selected_item.id` printed before `suggest_outfit` runs matches the dict passed into it; the printed `outfit_suggestion` text is exactly what gets fed to `create_fit_card`).
- **Easy early exit.** When `search_listings` returns empty twice, the loop sets `session["error"]` and returns. `selected_item` / `price_comparison` / `outfit_suggestion` / `fit_card` stay at their initialized `None`, so callers branch on the error field alone.

## Error Handling

| Tool | Failure mode | Agent response | Concrete observation from testing |
|---|---|---|---|
| `search_listings` | No listings match the query | Loop retries with the size filter dropped and `max_price` raised by 25%. If still empty, sets `session["error"]` and returns early — `selected_item` / `outfit_suggestion` / `fit_card` all stay `None`. | `python agent.py` no-results case (`"designer ballgown size XXS under $5"`) → primary search empty → broadened to size=None / $6.25 → still empty → error set, `fit_card is None`. Verified by the assertion in [agent.py:192](agent.py:192). |
| `compare_listing` | Missing fields, non-dict input, or no comparables in the dataset | Returns `None` (no exception). Loop tolerates the `None` and moves on. | `test_compare_listing_none_input_returns_none` and `test_compare_listing_unknown_category_returns_none` in [tests/test_tools.py](tests/test_tools.py) both pass — `compare_listing(None)` and `compare_listing({"category": "not_a_real_category", "price": 20})` each return `None`. |
| `suggest_outfit` | Empty wardrobe (`{"items": []}`) | Branches to a "no wardrobe yet" prompt that recommends generic staple pieces instead of named items, so the pipeline keeps flowing. | `test_suggest_outfit_with_empty_wardrobe` passes — calling with `{"items": []}` returns a non-empty stylist string. |
| `create_fit_card` | Empty or whitespace outfit string | Returns the literal string `"Error: Could not generate a fit card due to missing styling information."` — never raises. | Verified manually: `create_fit_card("", results[0])` prints exactly that message. Also covered by `test_create_fit_card_empty_outfit_returns_error_string` and `test_create_fit_card_whitespace_outfit_returns_error_string`. |

## Spec Reflection

**One way the spec helped.** The Error Handling table in [planning.md](planning.md) made me name a specific failure mode and a specific agent response for every tool *before* I wrote any code. That table turned into the test rows almost line-for-line (one test per row), and it's why the no-results branch was the first thing I implemented in `run_agent()` instead of an afterthought. Without the table I would have built the happy path first, discovered the empty-results bug in the demo, and bolted on the early-exit later — which is the bug the milestone explicitly warns about ("If your agent calls all three tools unconditionally regardless of what `search_listings` returns, the planning loop isn't working yet"). The spec made the right shape obvious upfront.

**What changed between planning.md and the working code:**

- **Query parsing.** planning.md called for a Groq LLM call to extract `description`, `size`, `max_price`. I went with regex instead (see `_PRICE_PHRASE_RE`, `_PRICE_BARE_RE`, `_SIZE_RE` in [agent.py:36](agent.py:36)). The regex is deterministic, free, and fast — and the queries in this assignment all match a small set of patterns ("under $X", "size M", etc.), so the LLM hop wasn't earning its cost.
- **Tool 2 (`suggest_outfit`) return type.** planning.md described it as returning `{"items": [...], "description": "..."}`. The implementation returns a single string of stylist notes that names the wardrobe pieces inline. This trades structured output for one less LLM-formatting step, and `create_fit_card` only ever needed the human-readable form anyway.
- **Tool 4 name.** planning.md uses both `compare_listing` and `compare_prices` interchangeably; the implementation settled on `compare_listing`.
- **Deal-rating thresholds.** planning.md didn't pin numbers. I picked ≤ −10% → Good Deal, ≤ +10% → Fair Price, else Overpriced. The 10% band keeps small dataset noise from flipping ratings.
- **Comparable narrowing.** planning.md said "same category and/or style tags." Implementation: start with same-category, and only narrow to tag-matched items if at least two exist — otherwise the average comes from a sample of one or two and the rating gets noisy.

What I'd change if I kept building:
- Have `suggest_outfit` return structured data (the list of wardrobe items actually used + the styling text) so the UI can highlight those wardrobe pieces, and so `create_fit_card` can reference items by name without re-parsing.
- Persist `search_results` beyond the top hit in the UI so a user can pick a different item.
- Make `compare_listing` weight comparables by recency or condition rather than averaging flat.

## Stretch Features Included

**Price Comparison Tool (+2pts).** `compare_listing(selected_item)` ([tools.py](tools.py)) is called at step 6 of the planning loop. **How comparisons are made:** the tool pulls all listings in the same category as the selected item (excluding the item itself), and if at least two of those also share a `style_tags` value with the selected item it narrows the comparable set to just those — otherwise it averages across the whole category. It then computes the percent difference between the item's price and that average and rates it Good Deal (≤ −10%) / Fair Price (within ±10%) / Overpriced (> +10%). Result is stored in `session["price_comparison"]` and surfaced in the listing panel of the Gradio app. Example from `python agent.py`: the Y2K Baby Tee at $18 is rated **Good Deal (avg $22.00, −18.2%)**.

**Retry Logic with Fallback (+1pt).** Step 4 of the planning loop handles a zero-result search by automatically retrying with **the size filter dropped and `max_price` raised by 25%**. A human-readable note describing exactly what was relaxed is stored in `session["fallback_adjusted"]` and shown to the user above the listing — e.g. "*No exact matches — broadened search (removed size filter; raised price ceiling to $6.25).*" Only if the broadened retry also returns nothing does the agent set `session["error"]` and abort. This is what makes the no-results test query (`"designer ballgown size XXS under $5"`) try a wider search before giving up.

## AI Usage

Two specific places I used Claude Code while building this.

**1. Implementing the planning loop in `run_agent()`.**

What I gave Claude as input:
- The "Planning Loop", "State Management", and "Architecture" sections of [planning.md](planning.md) (including the ASCII flow diagram).
- The existing scaffolding in [agent.py](agent.py): `_new_session()`, the `run_agent()` signature, and the TODO comments.
- The actual tool signatures from [tools.py](tools.py) — important because they differed slightly from planning.md (e.g. `suggest_outfit` returns `str`, not `dict`).

What it produced: a `run_agent()` that initialized the session, parsed the query, called all three tools in order, and returned the session.

What I overrode before keeping it:
- The first draft called `suggest_outfit` and `create_fit_card` even when `search_listings` returned an empty list. I rewrote the post-search step to branch — empty results trigger the fallback retry, and if that's also empty, the function returns the session immediately with `session["error"]` set. The CLI test in [agent.py](agent.py) ends with an `assert session2["fit_card"] is None` so this regression can't sneak back in.
- I added the broadened-search retry from planning.md step 4 (drop size, +25% price), which Claude's first draft skipped.
- I matched the tool call to the real signature (`suggest_outfit(item, wardrobe)` returning `str`, not the dict described in planning.md) instead of the spec-as-written.

**2. Writing the test suite for `compare_listing`.**

What I gave Claude as input:
- The existing tests in [tests/test_tools.py](tests/test_tools.py) for `search_listings`, `suggest_outfit`, and `create_fit_card` — so the new tests would match the same shape (one happy-path test per branch, plus targeted failure-mode tests).
- The "Error Handling" row for `compare_listing` from planning.md (failure returns `None`).
- The implementation in [tools.py](tools.py) so it could see the actual type guards and threshold logic.
- A snapshot of per-category price stats from the dataset (`tops: avg=21.73`, `outerwear: avg=44.00`, etc.) so the tests would use realistic prices that land in the right rating bucket.

What it produced: a set of tests covering the dict shape, each deal-rating bucket, and a generic invalid-input case.

What I overrode before keeping it:
- Added `test_compare_listing_excludes_the_item_itself` — Claude's draft didn't check that a listing wasn't allowed to be its own comparable, which would have masked a real bug. The test re-prices the real `lst_002` to $5 and asserts the rating doesn't get pulled toward its own original $18.
- Split the generic "invalid input" test into one test per failure mode (`none_input`, `non_dict_input`, `missing_price`, `missing_category`, `invalid_price_type`, `unknown_category`) so a regression points at which guard broke.
- Added `test_compare_listing_difference_percent_sign_matches_price` to pin the sign convention (negative = below average), since planning.md left "negative if the item is a deal" as the only spec.
