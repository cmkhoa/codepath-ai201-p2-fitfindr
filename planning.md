# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:** 
- Searches the  listings dataset and returns matching items. Must handle the case where no matches are found.
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): description of the piece
- `size` (str | None): the user's size preference, must be case-insensitive and partial overlaps (s = S = small = Small)
- `max_price` (float): the maximum price the user is willing to pay for the item

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
- 'listings' (list): a list representing clothing items, each items entry contains the title (str), platform (str), price(float), category (str), description (str), color (list[str]). Sorted by keyword matching score.


**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
- return an empty list. The planning loop should intercept this, storing an error in the session state explaining the error and exiting early with the matching response

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
- Suggests 1-2 complete outfits combinations using the new item + the user's wardrobe.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): the item the user just added to their wardrobe. with the same item shcema as items in the wardrobe.
- `wardrobe` (dict): the user's current wardrobe, containing an item list of wardrobe item dicts

**What it returns:**
<!-- Describe the return value -->
- items (list[dict]): The list of specific wardrobe item dictionaries selected from the user's wardrobe + the new item
- description (str): detailed outfit suggestions and styling tips What happens if it fails or returns nothing:

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
- the tool should state a fallback with general advice and stating that no outfits could be suggested. Format: {"items": [], "description": "<styling advice>"}

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
- Generate a short, sharable, and authentic outfit description (Instagram style) showcasing the selected listing item and styling suggestion.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (dict): A dictionary containing the outfit suggestion and styling tips from the suggest_outfit tool.
- selected_item (dict): the selected listing dictionary

**What it returns:**
<!-- Describe the return value -->
- caption (str): A 1-2 sentence short, casual, and authentic OOTD caption (Instagram style).


**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
- If the outfit dict is empty/invalid, it returns a descriptive error message string(e.g., "Error: Could not generate a fit card due to missing styling information") instead of throwing an exception.

---

### Additional Tools (if any)

### Tool 4: compare_listing

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
- Compares the price of the selected item with the average price of comparable listings in the database by querying the database and matching the same category and/or style tags.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- 'selected_item' (dict): The selected listing dictionary.


**What it returns:**
<!-- Describe the return value -->
- dict containing:
+ average_price (float): The average price of comparable items.
+ difference_percent (float): Percent difference (negative if the item is a deal).
+ deal_rating (str): "Good Deal", "Fair Price", or "Overpriced".

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
- Returns None

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
- The planning loop is orchestrated by run_agent() and follows a strict conditional execution path:

1. Initialization: Initialize the session state dictionary using _new_session(query, wardrobe).
2. Query Parsing: Use an LLM call to Groq to extract description (str), size (str or None), and max_price (float or None) from the raw user query. Store this structured data in session["parsed"].
3. Primary Search: Call search_listings(description, size, max_price).
4. Search Fallback Check:
If search results are returned: Proceed directly to Step 5.
If search results are empty:
Broaden the search constraints (remove the size filter and increase max_price by 25%).
Set a descriptive message in session["fallback_adjusted"] notifying the user of the adjustments.
Call search_listings again with the widened parameters.
If the fallback search also returns no results: Set session["error"] to a friendly message (e.g., advising the user to try different keywords) and terminate the agent early, returning the session state.
5. Selection: Store the full list of search results in session["search_results"]. Select the first (top-ranked) result as the target item and save it in session["selected_item"].
6. Price Comparison: Call compare_prices with session["selected_item"] and all listings to evaluate if the item is a good deal. Save the result in session["price_comparison"].
7. Outfit Generation: Call suggest_outfit(selected_item, wardrobe). Store the output dictionary (containing the wardrobe items used and the styling tips) in session["outfit_suggestion"].
8. Fit Card Generation: Call create_fit_card(outfit_suggestion, selected_item) using the LLM with higher temperature to generate a unique caption. Store it in session["fit_card"].
9. Return: The agent completes and returns the fully populated session dict.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
- The agent utilizes a centralized session dictionary initialized at the start of the interaction via _new_session().
- Data is passed sequentially: the return value of one tool is saved into the session state, and the planning loop extracts that specific data to use as arguments for the next tool.
- Tracked Data: raw_query, parsed_query (dict of description, size, max_price), search_results (list of matching items), selected_item (the top result), price_comparison (deal evaluation data), outfit_suggestion (styling text and utilized wardrobe items), and fit_card (social caption).
- By storing every intermediate step in the state, tools like create_fit_card can easily pull both the outfit_suggestion and the original selected_item to ensure no context is lost, even if previous steps triggered fallbacks.
---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | The agent intercepts the empty list, drops the size filter, increases max_price by 25%, and retries. If it fails again, it sets session["error"] with friendly advice to change keywords and aborts the loop early. |
| suggest_outfit | Wardrobe is empty | Intercepts the failure and defaults to general styling advice based on fashion rules instead of specific wardrobe items. Formats output as {"items": [], "description": "<general styling advice>"} to prevent pipeline breakage. |
| create_fit_card | Outfit input is missing or incomplete | Returns a descriptive error string (e.g., "Error: Could not generate a fit card due to missing styling information") rather than throwing a system exception, allowing the user to still see their search results and price check. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

---
```
[ User Input + Wardrobe ]
                   |
                   v
       [ Step 1: Parse Query ]  --> (Extracts terms, size, max_price)
                   |
                   v
    +---> [ Step 2: Search DB ]
    |              |
    |      (Match found?)
    |         /        \
    |       YES         NO --> [ Fallback: Broaden Params ]
    |        |                     (Price +25%, Drop Size)
    |        |                               |
    |        v                               v
    |  [ Select Item ]             (Still no matches?)
    |                                  /        \
    |                            Still NO       YES
    |                               /              \
    |                       [ Abort & Error ]       |
    |                                               |
    +-----------------------------------------------+
                   |
                   v
     =============================
     =   CENTRAL SESSION STATE   =  <-- (Holds selected_item & query)
     =============================
         |           |           |
         v           v           v
     [Step 3]    [Step 4]    [Step 5]
     Compare      Suggest    Create
     Price        Outfit     Fit Card
         \           |           /
          v          v          v
     =============================
     =   UPDATED SESSION STATE   =  <-- (Holds all final outputs)
     =============================
                   |
                   v
        [ Final Markdown Output ]
```

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
- AI Tool: Claude code.

- Input: I will provide the specific "Tools" section from this planning.md (e.g., input parameters, expected returns, failure modes) alongside a small JSON snippet of mock dataset structures (wardrobe schema, listing schema).

- Expectation: I expect complete Python functions with type hints, docstrings, and exact implementation of the fallback logic (e.g., returning an empty list for missing searches).

- Verification: Before moving on, I will write 3 basic unit tests for each function (Standard input, Edge Case/Empty input, Invalid type input) to verify the output format strictly matches the spec without throwing exceptions.

**Milestone 4 — Planning loop and state management:**
- AI Tool: Claude code.

- Input: I will provide the "Planning Loop," "State Management," and "Architecture" Mermaid diagram from this planning.md.

- Expectation: I expect a run_agent(query, wardrobe) function that initializes a dictionary, sequentially calls the tools built in Milestone 3, manages the fallback retry for search_listings, and handles the early exit perfectly.

- Verification: I will feed it a mock query and print out the session dictionary after every single step to ensure data is appending correctly without overwriting necessary previous state variables.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** The agent parses the query. Calls search_listings("vintage graphic tee", size=None, max_price=30.0) which returns 3 matching listings sorted by relevance. FitFindr picks the top result: "Faded Band Tee — $22, Depop, Good condition" and saves it to state.
<!-- What does the agent do first? Which tool is called? With what input? -->

**Step 2:** Calls compare_listing(selected_item=<band tee dict>) to evaluate the price. It queries the DB for graphic tees, returns {"average_price": 35.0, "difference_percent": -37.1, "deal_rating": "Good Deal"}, and saves it to state.
<!-- What happens next? What was returned from step 1? What tool is called now? -->

**Step 3:** Calls suggest_outfit(new_item=<band tee dict>, wardrobe=<user's wardrobe dict>). Recognizing the user's preference from the prompt/wardrobe data, it returns: {"items": [{"id": "jeans_01", "name": "Wide-leg light wash jeans"}], "description": "Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape."} and saves to state.
<!-- Continue until the full interaction is complete -->
**Step 4:** Calls create_fit_card(outfit=<outfit dict>, selected_item=<band tee dict>). It generates and returns: "Scored this faded vintage band tee for an absolute steal 🎸 Paired up with wide-leg denim and chunky stompers for the ultimate 90s vibe today. #OOTD #VintageFinds #Thrifted" and saves to state.
**Final output to user:**
<!-- What does the user actually see at the end? -->
- The agent takes the fully populated session state and formats a clean Markdown response showing:
+ The Find: The Faded Band Tee details, with a "Good Deal!" badge.
+ How to Wear It: The styling paragraph from Step 3.
+ Fit Card: The generated Instagram caption block from Step 4.
