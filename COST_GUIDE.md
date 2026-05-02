# Cost Management Guide

Running LLM functions at scale on Snowflake consumes credits quickly.
This guide covers how to estimate, control, and minimise costs for this project.

---

## Credit Consumption by Phase

| Phase | Function | Model | Est. credits per 1k rows |
|-------|----------|-------|--------------------------|
| 3 | CORTEX.TRANSLATE | auto | Low (only non-ASCII rows) |
| 4a | CORTEX.SENTIMENT | built-in | Low |
| 4b | CORTEX.COMPLETE | snowflake-arctic | Low-medium |
| 4b | CORTEX.COMPLETE | mistral-large | Medium |
| 5a | CORTEX.COMPLETE | mistral-large | High (long prompt + JSON) |
| 5b | CORTEX.COMPLETE | mistral-large2 | High (long input text) |

> Phases 5a and 5b are the most expensive. Always run on a sample first.

---

## Cost Control Commands

```sql
-- Suspend warehouse immediately
ALTER WAREHOUSE airline_ds_wh SUSPEND;

-- Set auto-suspend to 60 seconds
ALTER WAREHOUSE airline_ds_wh SET AUTO_SUSPEND = 60;

-- Disable auto-resume (strongest protection)
ALTER WAREHOUSE airline_ds_wh SET AUTO_RESUME = FALSE;

-- Downsize to X-SMALL (cheapest)
ALTER WAREHOUSE airline_ds_wh SET WAREHOUSE_SIZE = 'X-SMALL';

-- Check current usage this month
SELECT service_type, ROUND(SUM(credits_used), 2) AS credits
FROM snowflake.account_usage.metering_daily_history
WHERE usage_date >= DATE_TRUNC('month', CURRENT_DATE())
GROUP BY service_type ORDER BY credits DESC;
```

---

## Development Best Practices

**Always use LIMIT during development:**
```sql
-- Before running a full Cortex phase, test on 500 rows first
CREATE OR REPLACE TABLE airline_reviews_db.cortex_output.reviews_sentiment AS
SELECT *, SNOWFLAKE.CORTEX.SENTIMENT(review_english) AS sentiment_score
FROM airline_reviews_db.cortex_output.reviews_translated
LIMIT 500;  -- Remove this for full run
```

**Use cheaper models where possible:**
- Use `snowflake-arctic` instead of `mistral-large` for simple yes/no tasks
- Only use `mistral-large2` when the task genuinely requires it (long summarisation)

**Validate prompts on 50 rows before full runs:**
```sql
SELECT review_id,
       SNOWFLAKE.CORTEX.COMPLETE('mistral-large', 'your prompt here: ' || review_english) AS test_output
FROM airline_reviews_db.cortex_output.reviews_translated
LIMIT 50;
```

---

## Estimated Total Project Cost

Running the full pipeline on 23,617 rows (all phases):

| Scenario | Estimated Credits |
|----------|-----------------|
| Development (with LIMIT 500 each phase) | 5–15 credits |
| Full run (all 23k rows, all phases) | 200–300 credits |
| Re-run after prompt fix (single phase) | 20–50 credits |

> At ~$2–4 per credit, a full run costs approximately $400–$1,200.
> Use the phased checkpointing approach — fix issues on small samples,
> only do the full run once you're confident in the prompts.
