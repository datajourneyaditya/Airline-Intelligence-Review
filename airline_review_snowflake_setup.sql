-- ============================================================
-- AIRLINE REVIEW INTELLIGENCE PLATFORM
-- Snowflake SQL Setup Script — All Phases
-- Powered by Snowflake Cortex
-- ============================================================
-- USAGE:
--   1. Upload Airline_review.csv to your Snowflake internal stage (see Phase 1)
--   2. Run each phase section in a SQL Worksheet in Snowsight
--   3. Phases 3–5 use Cortex LLM functions (ensure your region supports them)
--      Supported regions: https://docs.snowflake.com/user-guide/snowflake-cortex/llm-functions#availability
-- ============================================================


-- ============================================================
-- PHASE 0 — ENVIRONMENT SETUP
-- Create database, schemas, warehouse
-- ============================================================

USE ROLE sysadmin;

-- Database
CREATE OR REPLACE DATABASE airline_reviews_db;

-- Schemas
CREATE OR REPLACE SCHEMA airline_reviews_db.raw;
CREATE OR REPLACE SCHEMA airline_reviews_db.harmonized;
CREATE OR REPLACE SCHEMA airline_reviews_db.analytics;
CREATE OR REPLACE SCHEMA airline_reviews_db.cortex_output;

-- Warehouse (medium for Cortex LLM workloads)
CREATE OR REPLACE WAREHOUSE airline_ds_wh
    WAREHOUSE_SIZE = 'medium'
    WAREHOUSE_TYPE = 'standard'
    AUTO_SUSPEND    = 120
    AUTO_RESUME     = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Warehouse for airline review AI analytics';

USE WAREHOUSE airline_ds_wh;
USE DATABASE airline_reviews_db;
USE SCHEMA raw;


-- ============================================================
-- PHASE 1 — DATA INGESTION
-- File format, internal stage, raw table, and CSV load
-- ============================================================

-- File format for CSV
CREATE OR REPLACE FILE FORMAT airline_reviews_db.public.csv_ff
    TYPE                = 'CSV'
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    SKIP_HEADER         = 1
    NULL_IF             = ('', 'NULL', 'null')
    EMPTY_FIELD_AS_NULL = TRUE
    TRIM_SPACE          = TRUE;

-- Internal stage (you will PUT the CSV file here)
CREATE OR REPLACE STAGE airline_reviews_db.public.airline_stage
    FILE_FORMAT = airline_reviews_db.public.csv_ff
    COMMENT     = 'Stage for Airline_review.csv upload';

-- To upload the file from your local machine, run in SnowSQL CLI:
--   PUT file:///path/to/Airline_review.csv @airline_reviews_db.public.airline_stage;
-- Or use Snowsight UI: Data > Add Data > Load files into a Stage

-- Raw ingestion table (mirrors CSV columns exactly)
CREATE OR REPLACE TABLE airline_reviews_db.raw.airline_reviews_raw (
    row_id                  NUMBER,
    airline_name            VARCHAR,
    overall_rating          NUMBER(3,1),
    review_title            VARCHAR,
    review_date             VARCHAR,        -- kept as string; parsed in harmonized layer
    verified                VARCHAR,
    review                  VARCHAR,
    aircraft                VARCHAR,
    type_of_traveller       VARCHAR,
    seat_type               VARCHAR,
    route                   VARCHAR,
    date_flown              VARCHAR,        -- kept as string; parsed in harmonized layer
    seat_comfort            NUMBER(3,1),
    cabin_staff_service     NUMBER(3,1),
    food_and_beverages      NUMBER(3,1),
    ground_service          NUMBER(3,1),
    inflight_entertainment  NUMBER(3,1),
    wifi_and_connectivity   NUMBER(3,1),
    value_for_money         NUMBER(3,1),
    recommended             VARCHAR
);

-- Load CSV from stage
COPY INTO airline_reviews_db.raw.airline_reviews_raw
FROM @airline_reviews_db.public.airline_stage
FILE_FORMAT = (FORMAT_NAME = 'airline_reviews_db.public.csv_ff')
ON_ERROR = 'CONTINUE';

-- Quick validation
SELECT COUNT(*) AS total_rows FROM airline_reviews_db.raw.airline_reviews_raw;
-- Expected: ~23,617 rows

SELECT airline_name, COUNT(*) AS review_count
FROM airline_reviews_db.raw.airline_reviews_raw
GROUP BY airline_name
ORDER BY review_count DESC
LIMIT 10;


-- ============================================================
-- PHASE 2 — HARMONIZED LAYER
-- Clean, parse dates, add a unique review_id, detect language
-- ============================================================

USE SCHEMA airline_reviews_db.harmonized;

-- Harmonized view with clean types and trimmed text
CREATE OR REPLACE VIEW airline_reviews_db.harmonized.airline_reviews_v AS
SELECT
    row_id                                                         AS review_id,
    TRIM(airline_name)                                             AS airline_name,
    overall_rating,
    TRIM(review_title)                                             AS review_title,

    -- Parse "11th November 2019" style dates safely
    TRY_TO_DATE(
        REGEXP_REPLACE(review_date, '(\\d+)(st|nd|rd|th)', '\\1'),
        'DD MMMM YYYY'
    )                                                              AS review_date,

    (verified = 'True')                                            AS verified,
    TRIM(review)                                                   AS review,
    NULLIF(TRIM(aircraft), '')                                     AS aircraft,
    TRIM(type_of_traveller)                                        AS traveller_type,
    TRIM(seat_type)                                                AS seat_type,
    TRIM(route)                                                    AS route,
    TRIM(date_flown)                                               AS date_flown,
    seat_comfort,
    cabin_staff_service,
    food_and_beverages,
    ground_service,
    inflight_entertainment,
    wifi_and_connectivity,
    value_for_money,
    LOWER(TRIM(recommended))                                       AS recommended,

    -- Computed: aspect average from the 7 structured scores (ignoring nulls)
    ROUND(
        (COALESCE(seat_comfort,0) + COALESCE(cabin_staff_service,0) +
         COALESCE(food_and_beverages,0) + COALESCE(ground_service,0) +
         COALESCE(inflight_entertainment,0) + COALESCE(wifi_and_connectivity,0) +
         COALESCE(value_for_money,0))
        /
        NULLIF(
            (CASE WHEN seat_comfort           IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN cabin_staff_service     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN food_and_beverages      IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN ground_service          IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN inflight_entertainment  IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN wifi_and_connectivity   IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN value_for_money         IS NOT NULL THEN 1 ELSE 0 END),
        0)
    , 2)                                                           AS avg_aspect_score

FROM airline_reviews_db.raw.airline_reviews_raw
WHERE review IS NOT NULL
  AND TRIM(review) != '';

-- Analytics pass-through view (query layer)
CREATE OR REPLACE VIEW airline_reviews_db.analytics.airline_reviews_v
    AS SELECT * FROM airline_reviews_db.harmonized.airline_reviews_v;

-- Spot check
SELECT airline_name, seat_type, traveller_type, overall_rating, review_date, review
FROM airline_reviews_db.analytics.airline_reviews_v
LIMIT 5;


-- ============================================================
-- PHASE 3 — CORTEX TRANSLATION
-- Translate non-English reviews to English
-- ============================================================

-- NOTE: Cortex LLM functions require Snowflake Enterprise or above
--       and must be run in a supported cloud region.

USE SCHEMA airline_reviews_db.cortex_output;

-- Step 3a: Detect likely non-English reviews using a heuristic
--          (reviews containing non-ASCII characters or short flag words)
--          For production, use SNOWFLAKE.CORTEX.TRANSLATE with auto language detection.

CREATE OR REPLACE TABLE airline_reviews_db.cortex_output.reviews_translated AS
SELECT
    review_id,
    airline_name,
    overall_rating,
    review_title,
    review_date,
    verified,
    traveller_type,
    seat_type,
    route,
    date_flown,
    seat_comfort,
    cabin_staff_service,
    food_and_beverages,
    ground_service,
    inflight_entertainment,
    wifi_and_connectivity,
    value_for_money,
    recommended,
    avg_aspect_score,
    review                                                         AS review_original,

    -- Translate all reviews (source language auto-detected, '' means auto)
    -- For large datasets, filter first to rows where review contains non-ASCII
    CASE
        WHEN review RLIKE '.*[^\x00-\x7F].*'
        THEN SNOWFLAKE.CORTEX.TRANSLATE(review, '', 'en')
        ELSE review
    END                                                            AS review_english

FROM airline_reviews_db.harmonized.airline_reviews_v;

-- Validation: check translation worked
SELECT review_original, review_english
FROM airline_reviews_db.cortex_output.reviews_translated
WHERE review_original != review_english
LIMIT 5;


-- ============================================================
-- PHASE 4A — CORTEX SENTIMENT SCORING
-- Add sentiment score (–1 = most negative, +1 = most positive)
-- ============================================================

CREATE OR REPLACE TABLE airline_reviews_db.cortex_output.reviews_sentiment AS
SELECT
    *,
    SNOWFLAKE.CORTEX.SENTIMENT(review_english)  AS sentiment_score,
    CASE
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(review_english) >= 0.2  THEN 'positive'
        WHEN SNOWFLAKE.CORTEX.SENTIMENT(review_english) <= -0.2 THEN 'negative'
        ELSE 'neutral'
    END                                         AS sentiment_label
FROM airline_reviews_db.cortex_output.reviews_translated;

-- Aggregated sentiment by airline
SELECT
    airline_name,
    COUNT(*)                        AS review_count,
    ROUND(AVG(sentiment_score), 3)  AS avg_sentiment,
    ROUND(AVG(overall_rating), 2)   AS avg_rating,
    SUM(CASE WHEN sentiment_label = 'positive' THEN 1 ELSE 0 END) AS positive_count,
    SUM(CASE WHEN sentiment_label = 'negative' THEN 1 ELSE 0 END) AS negative_count,
    SUM(CASE WHEN sentiment_label = 'neutral'  THEN 1 ELSE 0 END) AS neutral_count
FROM airline_reviews_db.cortex_output.reviews_sentiment
GROUP BY airline_name
ORDER BY avg_sentiment DESC;


-- ============================================================
-- PHASE 4B — INTENT TO RECOMMEND (Zero-shot classification)
-- Classify each review: Likely / Unlikely / Unsure to recommend
-- ============================================================

CREATE OR REPLACE TABLE airline_reviews_db.cortex_output.reviews_recommend AS
SELECT
    review_id,
    airline_name,
    overall_rating,
    seat_type,
    traveller_type,
    sentiment_score,
    sentiment_label,
    recommended                                                    AS recommended_raw,
    review_english,

    -- Zero-shot prompt: no examples given
    SNOWFLAKE.CORTEX.COMPLETE(
        'snowflake-arctic',
        CONCAT(
            '[INST]### ',
            'Based on the following airline customer review, will the passenger recommend ',
            'this airline to friends or family? Answer with only one word: ',
            '"Likely" or "Unlikely" or "Unsure". No additional text. ',
            'Review: ', review_english,
            ' ###[/INST]'
        )
    )                                                              AS recommend_raw_llm,

    -- Clean up LLM response
    CASE
        WHEN UPPER(TRIM(
            SNOWFLAKE.CORTEX.COMPLETE(
                'snowflake-arctic',
                CONCAT(
                    '[INST]### ',
                    'Based on the following airline customer review, will the passenger recommend ',
                    'this airline to friends or family? Answer with only one word: ',
                    '"Likely" or "Unlikely" or "Unsure". No additional text. ',
                    'Review: ', review_english,
                    ' ###[/INST]'
                )
            )
        )) LIKE '%LIKELY%'   THEN 'Likely'
        WHEN UPPER(TRIM(
            SNOWFLAKE.CORTEX.COMPLETE(
                'snowflake-arctic',
                CONCAT(
                    '[INST]### ',
                    'Based on the following airline customer review, will the passenger recommend ',
                    'this airline to friends or family? Answer with only one word: ',
                    '"Likely" or "Unlikely" or "Unsure". No additional text. ',
                    'Review: ', review_english,
                    ' ###[/INST]'
                )
            )
        )) LIKE '%UNLIKELY%' THEN 'Unlikely'
        ELSE 'Unsure'
    END                                                            AS recommend_llm_clean

FROM airline_reviews_db.cortex_output.reviews_sentiment;

-- NOTE: To avoid calling Complete 3x per row (expensive), use a CTE or Snowpark Python instead.
-- See the companion Snowpark notebook script for the efficient version.


-- ============================================================
-- PHASE 4C — TEXT RATING CLASSIFICATION (One-shot)
-- Derive awful / poor / okay / good / excellent from review text
-- ============================================================

-- Efficient pattern: compute once in a CTE, then clean

CREATE OR REPLACE TABLE airline_reviews_db.cortex_output.reviews_rated AS
WITH raw_ratings AS (
    SELECT
        review_id,
        airline_name,
        overall_rating,
        seat_type,
        traveller_type,
        review_english,
        sentiment_score,
        sentiment_label,
        recommended_raw,

        SNOWFLAKE.CORTEX.COMPLETE(
            'mistral-large',
            CONCAT(
                '[INST]### ',
                'You are rating airline customer reviews. ',
                'Rating must be exactly one of: awful, poor, okay, good, excellent. ',
                'awful = worst experience, excellent = best experience. ',
                'Output only the single rating word, nothing else. ',
                'Example review: "The crew was fantastic, seat was wide and the meal exceeded expectations." ',
                'Example rating: excellent ',
                'Rate this review: ', review_english,
                ' ###[/INST]'
            )
        ) AS rating_raw

    FROM airline_reviews_db.cortex_output.reviews_recommend
)
SELECT
    *,
    CASE
        WHEN LOWER(rating_raw) LIKE '%awful%'     THEN 'awful'
        WHEN LOWER(rating_raw) LIKE '%poor%'      THEN 'poor'
        WHEN LOWER(rating_raw) LIKE '%okay%'      THEN 'okay'
        WHEN LOWER(rating_raw) LIKE '%good%'      THEN 'good'
        WHEN LOWER(rating_raw) LIKE '%excellent%' THEN 'excellent'
        ELSE 'unsure'
    END AS rating_llm_clean
FROM raw_ratings;

-- Cross-validate LLM rating vs numeric overall_rating
SELECT
    rating_llm_clean,
    ROUND(AVG(overall_rating), 2)  AS avg_numeric_rating,
    COUNT(*)                        AS review_count
FROM airline_reviews_db.cortex_output.reviews_rated
GROUP BY rating_llm_clean
ORDER BY avg_numeric_rating DESC;


-- ============================================================
-- PHASE 5A — ASPECT-BASED SENTIMENT (One-shot, JSON output)
-- Extract per-review aspect sentiment using Cortex Complete
-- ============================================================

CREATE OR REPLACE TABLE airline_reviews_db.cortex_output.reviews_aspect_sentiment AS
SELECT
    review_id,
    airline_name,
    seat_type,
    traveller_type,
    overall_rating,
    sentiment_score,
    review_english,

    SNOWFLAKE.CORTEX.COMPLETE(
        'mistral-large',
        CONCAT(
            '[INST]### ',
            'Analyse this airline customer review and identify what the review says about these ',
            'categories: seat comfort, cabin crew, food and beverage, ground service, ',
            'inflight entertainment, wifi, value for money, baggage handling, delays and punctuality. ',
            'For each mentioned category, return sentiment as positive, neutral, or negative. ',
            'Return ONLY a valid JSON array. No extra text, no markdown. ',
            'Example: [{"category":"cabin crew","sentiment":"positive","detail":"very attentive"},',
            '{"category":"wifi","sentiment":"negative","detail":"did not work at all"}] ',
            'Review: ', review_english,
            ' ###[/INST]'
        )
    ) AS aspect_sentiment_json

FROM airline_reviews_db.cortex_output.reviews_rated;

-- Parse JSON and flatten to one row per aspect per review
-- Use PARSE_JSON and FLATTEN for downstream analysis

CREATE OR REPLACE VIEW airline_reviews_db.analytics.aspect_sentiment_flat_v AS
SELECT
    r.review_id,
    r.airline_name,
    r.seat_type,
    r.traveller_type,
    r.overall_rating,
    r.sentiment_score,
    f.value:category::VARCHAR   AS aspect_category,
    f.value:sentiment::VARCHAR  AS aspect_sentiment,
    f.value:detail::VARCHAR     AS aspect_detail
FROM airline_reviews_db.cortex_output.reviews_aspect_sentiment r,
     LATERAL FLATTEN(
         INPUT => TRY_PARSE_JSON(r.aspect_sentiment_json),
         OUTER => TRUE
     ) f
WHERE f.value:category IS NOT NULL;

-- Aggregate: aspect sentiment counts by airline
SELECT
    airline_name,
    aspect_category,
    COUNT(*)                                                      AS mentions,
    SUM(CASE WHEN aspect_sentiment = 'positive' THEN 1 ELSE 0 END) AS positive_mentions,
    SUM(CASE WHEN aspect_sentiment = 'negative' THEN 1 ELSE 0 END) AS negative_mentions,
    ROUND(
        SUM(CASE WHEN aspect_sentiment = 'positive' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1
    )                                                             AS positive_pct
FROM airline_reviews_db.analytics.aspect_sentiment_flat_v
WHERE aspect_category IS NOT NULL
GROUP BY airline_name, aspect_category
ORDER BY airline_name, negative_mentions DESC;


-- ============================================================
-- PHASE 5B — ISSUE IDENTIFICATION AT AIRLINE LEVEL
-- Find top 3 issues per airline from most negative reviews
-- ============================================================

-- Step 1: Identify airlines with enough reviews to be meaningful
CREATE OR REPLACE TABLE airline_reviews_db.cortex_output.airline_issue_summary AS
WITH qualified_airlines AS (
    SELECT airline_name
    FROM airline_reviews_db.cortex_output.reviews_rated
    GROUP BY airline_name
    HAVING COUNT(*) >= 20
),
-- Step 2: Aggregate the 100 most negative reviews per airline into one text block
negative_review_agg AS (
    SELECT
        r.airline_name,
        LISTAGG(r.review_english, ' | ') WITHIN GROUP (ORDER BY r.sentiment_score ASC) AS agg_reviews,
        COUNT(*) AS review_count,
        ROUND(AVG(r.sentiment_score), 3) AS avg_sentiment,
        ROUND(AVG(r.overall_rating), 2) AS avg_rating
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY airline_name ORDER BY sentiment_score ASC) AS rn
        FROM airline_reviews_db.cortex_output.reviews_rated
    ) r
    JOIN qualified_airlines qa ON r.airline_name = qa.airline_name
    WHERE r.rn <= 100
    GROUP BY r.airline_name
)
-- Step 3: Ask Cortex Complete to summarise issues and recommend fixes
SELECT
    airline_name,
    avg_sentiment,
    avg_rating,
    review_count,

    SNOWFLAKE.CORTEX.COMPLETE(
        'mistral-large2',
        CONCAT(
            '[INST]### ',
            'You are a customer experience analyst for an airline. ',
            'Based on the following aggregated customer reviews for airline: ', airline_name, ', ',
            'identify exactly 3 main issues passengers are facing. ',
            'Format your response as 3 bullet points. Each bullet must have: ',
            '1) A short bold heading (3–5 words), ',
            '2) A one-sentence description of the issue (under 40 words), ',
            '3) A one-sentence recommendation to fix it. ',
            'Keep the entire response under 200 words. ',
            'Reviews: ', LEFT(agg_reviews, 8000),
            ' ###[/INST]'
        )
    ) AS top_issues_summary

FROM negative_review_agg;

-- View results
SELECT airline_name, avg_rating, avg_sentiment, top_issues_summary
FROM airline_reviews_db.cortex_output.airline_issue_summary
ORDER BY avg_sentiment ASC
LIMIT 10;


-- ============================================================
-- PHASE 5C — COMPETITOR COMPARISON
-- Side-by-side aspect scores and sentiment for any two airlines
-- ============================================================

-- Parameterised query — swap the two airline names as needed
-- In Streamlit this will be driven by a selectbox

SELECT
    aspect_category,

    -- Airline A
    SUM(CASE WHEN airline_name = 'British Airways' AND aspect_sentiment = 'positive' THEN 1 ELSE 0 END)
        AS ba_positive,
    SUM(CASE WHEN airline_name = 'British Airways' AND aspect_sentiment = 'negative' THEN 1 ELSE 0 END)
        AS ba_negative,
    SUM(CASE WHEN airline_name = 'British Airways' THEN 1 ELSE 0 END)
        AS ba_total,

    -- Airline B
    SUM(CASE WHEN airline_name = 'Emirates' AND aspect_sentiment = 'positive' THEN 1 ELSE 0 END)
        AS em_positive,
    SUM(CASE WHEN airline_name = 'Emirates' AND aspect_sentiment = 'negative' THEN 1 ELSE 0 END)
        AS em_negative,
    SUM(CASE WHEN airline_name = 'Emirates' THEN 1 ELSE 0 END)
        AS em_total,

    -- Positive % for each
    ROUND(SUM(CASE WHEN airline_name = 'British Airways' AND aspect_sentiment = 'positive' THEN 1 ELSE 0 END) * 100.0
          / NULLIF(SUM(CASE WHEN airline_name = 'British Airways' THEN 1 ELSE 0 END), 0), 1)
        AS ba_positive_pct,

    ROUND(SUM(CASE WHEN airline_name = 'Emirates' AND aspect_sentiment = 'positive' THEN 1 ELSE 0 END) * 100.0
          / NULLIF(SUM(CASE WHEN airline_name = 'Emirates' THEN 1 ELSE 0 END), 0), 1)
        AS em_positive_pct

FROM airline_reviews_db.analytics.aspect_sentiment_flat_v
WHERE airline_name IN ('British Airways', 'Emirates')
  AND aspect_category IS NOT NULL
GROUP BY aspect_category
ORDER BY aspect_category;


-- ============================================================
-- PHASE 6 — ANALYTICS VIEWS FOR STREAMLIT DASHBOARD
-- Pre-aggregated views to power each dashboard tab
-- ============================================================

USE SCHEMA airline_reviews_db.analytics;

-- View 1: Overall KPIs per airline (Overview tab)
CREATE OR REPLACE VIEW airline_reviews_db.analytics.v_airline_kpis AS
SELECT
    airline_name,
    COUNT(*)                                                      AS total_reviews,
    ROUND(AVG(overall_rating), 2)                                 AS avg_rating,
    ROUND(AVG(sentiment_score), 3)                                AS avg_sentiment,
    SUM(CASE WHEN recommended_raw = 'yes' THEN 1 ELSE 0 END)     AS recommended_count,
    ROUND(SUM(CASE WHEN recommended_raw = 'yes' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1)
                                                                  AS recommended_pct,
    ROUND(AVG(seat_comfort), 2)                                   AS avg_seat_comfort,
    ROUND(AVG(cabin_staff_service), 2)                            AS avg_cabin_staff,
    ROUND(AVG(food_and_beverages), 2)                             AS avg_food,
    ROUND(AVG(ground_service), 2)                                 AS avg_ground_service,
    ROUND(AVG(inflight_entertainment), 2)                         AS avg_ife,
    ROUND(AVG(wifi_and_connectivity), 2)                          AS avg_wifi,
    ROUND(AVG(value_for_money), 2)                                AS avg_value
FROM airline_reviews_db.cortex_output.reviews_rated
GROUP BY airline_name;

-- View 2: Sentiment over time (Sentiment tab)
CREATE OR REPLACE VIEW airline_reviews_db.analytics.v_sentiment_over_time AS
SELECT
    airline_name,
    DATE_TRUNC('month', review_date)                              AS review_month,
    COUNT(*)                                                      AS review_count,
    ROUND(AVG(sentiment_score), 3)                                AS avg_sentiment,
    ROUND(AVG(overall_rating), 2)                                 AS avg_rating
FROM airline_reviews_db.cortex_output.reviews_rated
WHERE review_date IS NOT NULL
GROUP BY airline_name, DATE_TRUNC('month', review_date)
ORDER BY airline_name, review_month;

-- View 3: Aspect scores by seat class (Aspects tab)
CREATE OR REPLACE VIEW airline_reviews_db.analytics.v_aspects_by_class AS
SELECT
    airline_name,
    seat_type,
    ROUND(AVG(seat_comfort), 2)          AS avg_seat_comfort,
    ROUND(AVG(cabin_staff_service), 2)   AS avg_cabin_staff,
    ROUND(AVG(food_and_beverages), 2)    AS avg_food,
    ROUND(AVG(ground_service), 2)        AS avg_ground_service,
    ROUND(AVG(inflight_entertainment), 2) AS avg_ife,
    ROUND(AVG(wifi_and_connectivity), 2) AS avg_wifi,
    ROUND(AVG(value_for_money), 2)       AS avg_value,
    COUNT(*)                             AS review_count
FROM airline_reviews_db.cortex_output.reviews_rated
WHERE seat_type IS NOT NULL
GROUP BY airline_name, seat_type;

-- View 4: LLM aspect sentiment for radar chart (Aspects tab)
CREATE OR REPLACE VIEW airline_reviews_db.analytics.v_llm_aspect_scores AS
SELECT
    airline_name,
    aspect_category,
    COUNT(*)                                                         AS total_mentions,
    SUM(CASE WHEN aspect_sentiment = 'positive' THEN 1 ELSE 0 END)  AS positive_ct,
    SUM(CASE WHEN aspect_sentiment = 'negative' THEN 1 ELSE 0 END)  AS negative_ct,
    ROUND(
        SUM(CASE WHEN aspect_sentiment = 'positive' THEN 1.0
                 WHEN aspect_sentiment = 'negative' THEN -1.0
                 ELSE 0 END) / COUNT(*), 3
    )                                                                AS net_sentiment_score
FROM airline_reviews_db.analytics.aspect_sentiment_flat_v
WHERE aspect_category IS NOT NULL
GROUP BY airline_name, aspect_category;

-- View 5: Traveller type breakdown (Overview tab)
CREATE OR REPLACE VIEW airline_reviews_db.analytics.v_traveller_breakdown AS
SELECT
    airline_name,
    traveller_type,
    seat_type,
    COUNT(*)                          AS review_count,
    ROUND(AVG(overall_rating), 2)     AS avg_rating,
    ROUND(AVG(sentiment_score), 3)    AS avg_sentiment,
    ROUND(
        SUM(CASE WHEN recommended_raw = 'yes' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1
    )                                 AS recommended_pct
FROM airline_reviews_db.cortex_output.reviews_rated
GROUP BY airline_name, traveller_type, seat_type;

-- View 6: Most-negative reviews per airline for Issues tab
CREATE OR REPLACE VIEW airline_reviews_db.analytics.v_worst_reviews AS
SELECT
    review_id,
    airline_name,
    overall_rating,
    sentiment_score,
    traveller_type,
    seat_type,
    route,
    review_english,
    rating_llm_clean,
    ROW_NUMBER() OVER (PARTITION BY airline_name ORDER BY sentiment_score ASC) AS rank_within_airline
FROM airline_reviews_db.cortex_output.reviews_rated;

-- View 7: Issue summaries for Issues tab
CREATE OR REPLACE VIEW airline_reviews_db.analytics.v_airline_issues AS
SELECT
    airline_name,
    avg_rating,
    avg_sentiment,
    review_count,
    top_issues_summary
FROM airline_reviews_db.cortex_output.airline_issue_summary
ORDER BY avg_sentiment ASC;


-- ============================================================
-- PHASE 6B — ON-DEMAND AI REPORT (called from Streamlit)
-- Run this query from Streamlit, passing the airline name dynamically
-- ============================================================

-- Template — replace :airline_name with the selected airline in Streamlit
-- In Streamlit Python this becomes a parameterised execute() call

/*
SELECT
    SNOWFLAKE.CORTEX.COMPLETE(
        'mistral-large2',
        CONCAT(
            '[INST]### ',
            'Write a formal improvement brief email to the franchise operations manager at ', :airline_name, '. ',
            'Address it from the Customer Intelligence Team. ',
            'Summarise the top 3 passenger experience issues based on the following aggregated reviews, ',
            'with clear headings, one paragraph per issue, and a specific operational recommendation for each. ',
            'Keep it under 300 words and professional in tone. ',
            'Reviews: ', :aggregated_reviews,
            ' ###[/INST]'
        )
    ) AS improvement_brief;
*/


-- ============================================================
-- VALIDATION QUERIES — run after each phase to confirm output
-- ============================================================

-- Check row counts through the pipeline
SELECT 'raw'               AS layer, COUNT(*) AS rows FROM airline_reviews_db.raw.airline_reviews_raw
UNION ALL
SELECT 'harmonized'        AS layer, COUNT(*) AS rows FROM airline_reviews_db.harmonized.airline_reviews_v
UNION ALL
SELECT 'translated'        AS layer, COUNT(*) AS rows FROM airline_reviews_db.cortex_output.reviews_translated
UNION ALL
SELECT 'sentiment'         AS layer, COUNT(*) AS rows FROM airline_reviews_db.cortex_output.reviews_sentiment
UNION ALL
SELECT 'rated'             AS layer, COUNT(*) AS rows FROM airline_reviews_db.cortex_output.reviews_rated
UNION ALL
SELECT 'aspect_sentiment'  AS layer, COUNT(*) AS rows FROM airline_reviews_db.cortex_output.reviews_aspect_sentiment
UNION ALL
SELECT 'issue_summaries'   AS layer, COUNT(*) AS rows FROM airline_reviews_db.cortex_output.airline_issue_summary;

-- Top 5 airlines by average sentiment (sanity check)
SELECT airline_name, avg_sentiment, avg_rating, total_reviews
FROM airline_reviews_db.analytics.v_airline_kpis
WHERE total_reviews >= 20
ORDER BY avg_sentiment DESC
LIMIT 5;

-- Bottom 5 airlines (most issues)
SELECT airline_name, avg_sentiment, avg_rating, total_reviews
FROM airline_reviews_db.analytics.v_airline_kpis
WHERE total_reviews >= 20
ORDER BY avg_sentiment ASC
LIMIT 5;

-- ============================================================
-- END OF SCRIPT
-- Next step: Run the companion Streamlit app (airline_streamlit_app.py)
-- ============================================================
