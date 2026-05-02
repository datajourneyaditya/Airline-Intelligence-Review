# Prompt Engineering Notes

This document captures the prompt design decisions made in Phase 4b and 5a
of the pipeline — useful for anyone adapting the project or interviewing the author.

---

## Phase 4b — Recommend Intent Classification

**Model:** `snowflake-arctic` (zero-shot)

**Why zero-shot?**
The task is simple binary classification with a limited output space
(Likely / Unlikely / Unsure). The model doesn't need an example to understand
the task structure — zero-shot is cheaper and faster.

**Prompt structure:**
```
[INST]### Based on this airline review, will the passenger recommend
this airline? Reply with exactly one word: Likely, Unlikely, or Unsure.
No extra text. Review: {review_english} ###[/INST]
```

**Key constraints:**
- "Reply with exactly one word" — reduces verbose responses
- Named the exact three valid options — prevents hallucinated variants
- "No extra text" — reduces markdown and preamble in output

---

## Phase 4b — Text Rating Classification

**Model:** `mistral-large` (one-shot)

**Why one-shot?**
Zero-shot produced outputs like "I would rate this as good" or "Rating: 3/5"
instead of the single word required. A worked example anchors the exact
output format expected.

**Prompt structure:**
```
[INST]### Rate this airline review with one word only:
awful, poor, okay, good, or excellent. No extra text.
Example: Fantastic crew, smooth flight. Rating: excellent
Rate this review: {review_english} ###[/INST]
```

**Iteration history:**
- v1 (zero-shot): ~60% single-word compliance
- v2 (added "No extra text"): ~75% compliance
- v3 (added one-shot example): ~99% compliance

---

## Phase 5a — Aspect-Based JSON Extraction

**Model:** `mistral-large` (one-shot)

**Why one-shot?**
This is the most complex prompt in the pipeline — the model needs to:
1. Identify which of 9 categories are mentioned
2. Determine sentiment for each
3. Return a specific JSON array structure

Zero-shot produced inconsistent JSON (sometimes wrapped in markdown code
blocks, sometimes plain text, sometimes missing fields).

**Prompt structure:**
```
[INST]### Analyse this airline review. Identify what it says about:
seat comfort, cabin crew, food and beverage, ground service,
inflight entertainment, wifi, value for money, baggage handling, delays.
For each mentioned category return: category, sentiment, detail.
Return ONLY a valid JSON array, no markdown, no extra text.
Example: [{"category":"cabin crew","sentiment":"positive","detail":"attentive"},
{"category":"wifi","sentiment":"negative","detail":"broken"}]
Review: {review_english} ###[/INST]
```

**Key constraints:**
- "Return ONLY a valid JSON array" — critical for LATERAL FLATTEN downstream
- "no markdown, no extra text" — prevents ```json wrapping
- One complete worked example — anchors both structure and value types
- TRY_PARSE_JSON used instead of PARSE_JSON — malformed output returns NULL not error

**Parse failure rate:**
- Zero-shot: ~35-40% parse failure
- One-shot (v1, no "no markdown"): ~15% failure
- One-shot (v2, with all constraints): ~1-2% failure

---

## Phase 5b — Issue Summarisation

**Model:** `mistral-large2` (structured instruction)

**Why mistral-large2?**
Longer input (aggregated 100 reviews) and longer output (3-bullet structured
brief) benefit from the stronger instruction-following of large2 vs large.

**Why not one-shot here?**
The output is free-form prose with specific formatting requirements. A
single worked example would be too long to include efficiently and might
over-anchor the style. Structured instruction works better for this task.

**Prompt structure:**
```
[INST]### CX analyst task for airline: {airline_name}.
From these reviews identify 3 main passenger issues.
Format: 3 bullets each with bold heading (3-5 words),
one sentence issue, one sentence fix. Under 200 words.
Reviews: {LEFT(agg_text, 8000)} ###[/INST]
```

**Key design decisions:**
- `LEFT(agg_text, 8000)` — caps input tokens to control cost
- Word limit in prompt — prevents verbose multi-paragraph responses
- Bold heading instruction — makes output scannable in the dashboard
- "one sentence issue, one sentence fix" — enforces diagnostic + prescriptive structure

---

## General Principles Applied

1. **Be explicit about format** — always state exactly what the output should look like
2. **Enumerate valid options** — for classification, list every valid response value
3. **Forbid what you don't want** — "no markdown", "no extra text", "no preamble"
4. **Use one-shot for structured output** — a single worked example outperforms
   multiple constraints for JSON/structured tasks
5. **Fail safely** — `TRY_PARSE_JSON` over `PARSE_JSON`, `TRY_TO_DATE` over `TO_DATE`
6. **Test on 500 rows first** — validate prompt compliance before full-scale run
7. **Document failure modes** — track what the zero-shot version produced and why it failed
