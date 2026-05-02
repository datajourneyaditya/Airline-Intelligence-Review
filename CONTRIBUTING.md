# Contributing to Airline Review Intelligence Platform

Thank you for your interest! Here's how to use, adapt, and contribute.

---

## 🚀 Running the project

See the full setup guide in [README.md](README.md).

**Quick start checklist:**
- [ ] Snowflake account with Cortex LLM enabled in your region
- [ ] Upload `data/Airline_review.csv` to Snowflake internal stage
- [ ] Run `sql/01_setup.sql` (all 6 phases)
- [ ] Run `sql/02_fix_date_parsing.sql`
- [ ] Import notebook and deploy Streamlit app
- [ ] Packages for Streamlit: `plotly`, `snowflake-snowpark-python` only

---

## 🔁 Adapting to a different domain

1. Replace `data/Airline_review.csv` with your own review dataset
2. Update column names in Phase 2 of `sql/01_setup.sql` (harmonized view)
3. Update the aspect category list in the Phase 5a `CORTEX.COMPLETE` prompt
4. Update `aspect_cols` dictionary in `streamlit/airline_streamlit_app.py`
5. Everything else works without changes

---

## 🐛 Reporting bugs

Open a GitHub Issue with:
- [ ] Phase number where the issue occurred (0–6)
- [ ] Snowflake region and edition (Standard / Enterprise)
- [ ] Error message (full text)
- [ ] Expected vs actual behaviour

---

## 💡 Common issues

| Issue | Fix |
|-------|-----|
| `KeyError: AVG_GROUND_SERVICE` | Run `sql/02_fix_date_parsing.sql` which also fixes view column aliases |
| Sentiment trend shows blank | Date parsing failed — check `ROWS_WITH_DATE` using validation query in README |
| Cortex Complete error | Verify your Snowflake region supports LLM functions |
| Package conflict on Streamlit | Remove `snowflake-ml-python` and `pandas` from packages panel |
| Blank competitor compare chart | Click "Compare airlines →" in sidebar first, then open the ⚔️ Compare tab |
