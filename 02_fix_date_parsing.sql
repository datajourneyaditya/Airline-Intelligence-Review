-- ============================================================
-- FIX: Harmonized view date parsing + sentiment over time view
-- Run this in a Snowflake SQL Worksheet
-- ============================================================
-- Problem: TRY_TO_DATE returned NULL for all rows because
--          Snowflake REGEXP_REPLACE uses \1 (single backslash)
--          not \\1 for backreferences, and the format string
--          'DD MMMM YYYY' requires a zero-padded day which
--          single-digit days (e.g. "6 September") don't have.
-- ============================================================

USE DATABASE airline_reviews_db;
USE SCHEMA harmonized;
USE WAREHOUSE airline_ds_wh;


-- ── Step 1: Verify the fix works on sample rows ───────────────────────────
-- Run this first to confirm before recreating the view
SELECT
    review_date                                                 AS raw_date,

    -- Step A: strip ordinal suffix (st/nd/rd/th) — Snowflake uses \1 not \\1
    REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1') AS step_a_stripped,

    -- Step B: LPAD the day number to 2 digits so '6 September 2019' → '06 September 2019'
    LPAD(
        SPLIT_PART(
            REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
            ' ', 1
        ),
        2, '0'
    ) || ' ' ||
    SPLIT_PART(
        REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
        ' ', 2
    ) || ' ' ||
    SPLIT_PART(
        REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
        ' ', 3
    )                                                           AS step_b_padded,

    -- Step C: parse to date
    TRY_TO_DATE(
        LPAD(
            SPLIT_PART(
                REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
                ' ', 1
            ), 2, '0'
        ) || ' ' ||
        SPLIT_PART(
            REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
            ' ', 2
        ) || ' ' ||
        SPLIT_PART(
            REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
            ' ', 3
        ),
        'DD MMMM YYYY'
    )                                                           AS parsed_date

FROM airline_reviews_db.raw.airline_reviews_raw
WHERE review_date IS NOT NULL
LIMIT 20;


-- ── Step 2: Count how many rows parse successfully ────────────────────────
SELECT
    COUNT(*)                   AS total_rows,
    COUNT(
        TRY_TO_DATE(
            LPAD(
                SPLIT_PART(
                    REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
                    ' ', 1
                ), 2, '0'
            ) || ' ' ||
            SPLIT_PART(
                REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
                ' ', 2
            ) || ' ' ||
            SPLIT_PART(
                REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
                ' ', 3
            ),
            'DD MMMM YYYY'
        )
    )                          AS rows_parsed_ok,
    total_rows - rows_parsed_ok AS rows_still_null
FROM airline_reviews_db.raw.airline_reviews_raw
WHERE review_date IS NOT NULL;


-- ── Step 3: Recreate the harmonized view with the fixed date parser ───────
CREATE OR REPLACE VIEW airline_reviews_db.harmonized.airline_reviews_v AS
SELECT
    row_id                                                          AS review_id,
    TRIM(airline_name)                                              AS airline_name,
    overall_rating,
    TRIM(review_title)                                              AS review_title,

    -- Fixed date parser: strip ordinal + LPAD day + TRY_TO_DATE
    TRY_TO_DATE(
        LPAD(
            SPLIT_PART(
                REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
                ' ', 1
            ), 2, '0'
        ) || ' ' ||
        SPLIT_PART(
            REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
            ' ', 2
        ) || ' ' ||
        SPLIT_PART(
            REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
            ' ', 3
        ),
        'DD MMMM YYYY'
    )                                                               AS review_date,

    (verified = 'True')                                             AS verified,
    TRIM(review)                                                    AS review,
    NULLIF(TRIM(aircraft), '')                                      AS aircraft,
    TRIM(type_of_traveller)                                         AS traveller_type,
    TRIM(seat_type)                                                 AS seat_type,
    TRIM(route)                                                     AS route,
    TRIM(date_flown)                                                AS date_flown,
    seat_comfort,
    cabin_staff_service,
    food_and_beverages,
    ground_service,
    inflight_entertainment,
    wifi_and_connectivity,
    value_for_money,
    LOWER(TRIM(recommended))                                        AS recommended,

    -- Null-safe composite aspect score
    ROUND(
        (COALESCE(seat_comfort, 0) + COALESCE(cabin_staff_service, 0) +
         COALESCE(food_and_beverages, 0) + COALESCE(ground_service, 0) +
         COALESCE(inflight_entertainment, 0) + COALESCE(wifi_and_connectivity, 0) +
         COALESCE(value_for_money, 0))
        / NULLIF(
            (CASE WHEN seat_comfort           IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN cabin_staff_service     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN food_and_beverages      IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN ground_service          IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN inflight_entertainment  IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN wifi_and_connectivity   IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN value_for_money         IS NOT NULL THEN 1 ELSE 0 END), 0)
    , 2)                                                            AS avg_aspect_score

FROM airline_reviews_db.raw.airline_reviews_raw
WHERE review IS NOT NULL
  AND TRIM(review) != '';


-- ── Step 4: Recreate the analytics pass-through view ─────────────────────
CREATE OR REPLACE VIEW airline_reviews_db.analytics.airline_reviews_v
    AS SELECT * FROM airline_reviews_db.harmonized.airline_reviews_v;


-- ── Step 5: Patch review_date into the existing reviews_rated table ───────
-- The enriched tables already exist but were built with NULL review_date.
-- This UPDATE patches the date column without re-running the expensive LLM pipeline.
UPDATE airline_reviews_db.cortex_output.reviews_translated   t
SET    t.review_date = h.review_date
FROM   airline_reviews_db.harmonized.airline_reviews_v       h
WHERE  t.review_id = h.review_id
  AND  h.review_date IS NOT NULL;

UPDATE airline_reviews_db.cortex_output.reviews_sentiment    t
SET    t.review_date = h.review_date
FROM   airline_reviews_db.harmonized.airline_reviews_v       h
WHERE  t.review_id = h.review_id
  AND  h.review_date IS NOT NULL;

UPDATE airline_reviews_db.cortex_output.reviews_rated        t
SET    t.review_date = h.review_date
FROM   airline_reviews_db.harmonized.airline_reviews_v       h
WHERE  t.review_id = h.review_id
  AND  h.review_date IS NOT NULL;


-- ── Step 6: Recreate the sentiment over time view with fixed dates ─────────
CREATE OR REPLACE VIEW airline_reviews_db.analytics.v_sentiment_over_time AS
SELECT
    airline_name,
    DATE_TRUNC('month', review_date)            AS review_month,
    COUNT(*)                                    AS review_count,
    ROUND(AVG(sentiment_score), 3)              AS avg_sentiment,
    ROUND(AVG(overall_rating), 2)               AS avg_rating
FROM airline_reviews_db.cortex_output.reviews_rated
WHERE review_date IS NOT NULL
GROUP BY airline_name, DATE_TRUNC('month', review_date)
ORDER BY airline_name, review_month;


-- ── Step 7: Validate — should now show real dates ─────────────────────────
SELECT
    COUNT(*)              AS total_rows,
    COUNT(review_date)    AS rows_with_date,
    MIN(review_date)      AS earliest,
    MAX(review_date)      AS latest
FROM airline_reviews_db.cortex_output.reviews_rated;

-- Should also show monthly data points now
SELECT airline_name, review_month, review_count, avg_sentiment
FROM airline_reviews_db.analytics.v_sentiment_over_time
ORDER BY review_month DESC
LIMIT 20;
