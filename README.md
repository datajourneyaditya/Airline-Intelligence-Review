# ✈️ Airline Review Intelligence Platform

> End-to-end AI-powered review analytics pipeline built entirely on **Snowflake Cortex**

[![Snowflake](https://img.shields.io/badge/Snowflake-Cortex-29B5E8?logo=snowflake&logoColor=white)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/llm-functions)
[![Streamlit](https://img.shields.io/badge/Streamlit-in%20Snowflake-FF4B4B?logo=streamlit&logoColor=white)](https://docs.snowflake.com/en/developer-guide/streamlit/about-streamlit)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📌 Overview

A production-quality data platform that processes **23,617 real airline customer reviews** across **50+ airlines** through a 6-phase AI enrichment pipeline — multilingual translation, sentiment scoring, aspect-based JSON extraction, issue identification, and on-demand LLM report generation — all without a single byte of data leaving Snowflake's governance boundary.

The project is delivered as **three independent, production-ready deliverables**:

| Deliverable | File | Description |
|-------------|------|-------------|
| 📄 SQL Pipeline | `sql/01_setup.sql` | 740-line, 6-phase Snowflake pipeline |
| 📓 Notebook | `notebook/airline_review_cortex_notebook.ipynb` | 31-cell Snowflake Notebook with 5 chart types |
| 💻 Streamlit App | `streamlit/airline_streamlit_app.py` | 7-tab live dashboard, 1000+ lines |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Snowflake Platform                            │
│                                                                      │
│   CSV Upload                                                         │
│      │                                                               │
│      ▼                                                               │
│  ┌─────────┐    ┌─────────────┐    ┌───────────┐    ┌────────────┐ │
│  │   raw   │───▶│ harmonized  │───▶│ analytics │    │cortex_out  │ │
│  │ schema  │    │   schema    │    │  schema   │    │   put      │ │
│  │         │    │ (clean,     │    │ (views,   │    │ (LLM enri- │ │
│  │ verbatim│    │  typed,     │    │  KPIs)    │    │  chment)   │ │
│  │ ingest  │    │  dated)     │    │           │    │            │ │
│  └─────────┘    └─────────────┘    └───────────┘    └────────────┘ │
│                                                            │         │
│              Snowflake Cortex LLM Functions                │         │
│         TRANSLATE · SENTIMENT · COMPLETE (3 models)        │         │
│                                                            ▼         │
│                                              ┌──────────────────┐   │
│                                              │  Streamlit App   │   │
│                                              │   (7 tabs)       │   │
│                                              └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 Pipeline Phases

| Phase | Description | Key Snowflake Feature |
|-------|-------------|----------------------|
| **0** | Environment — database, schemas, warehouse | DDL |
| **1** | CSV ingestion via internal stage | `COPY INTO`, File Formats |
| **2** | Harmonized view — date parsing, null-safe scoring | `TRY_TO_DATE`, `COALESCE`, `LPAD` |
| **3** | Multilingual translation | `CORTEX.TRANSLATE` |
| **4a** | Sentiment scoring per review | `CORTEX.SENTIMENT` |
| **4b** | Text rating + recommend intent classification | `CORTEX.COMPLETE` (zero-shot + one-shot) |
| **5a** | Aspect-based JSON sentiment extraction | `CORTEX.COMPLETE` + `LATERAL FLATTEN` |
| **5b** | Per-airline issue summarisation | `CORTEX.COMPLETE` (mistral-large2) |
| **6** | Analytics views + Streamlit dashboard | Streamlit in Snowflake |

---

## 🤖 Cortex LLM Functions

| Function | Model | Task | Prompting Strategy |
|----------|-------|------|--------------------|
| `CORTEX.TRANSLATE` | auto | Non-English → English | N/A |
| `CORTEX.SENTIMENT` | built-in | Score –1 to +1 per review | N/A |
| `CORTEX.COMPLETE` | `snowflake-arctic` | Recommend intent (Likely/Unlikely) | Zero-shot |
| `CORTEX.COMPLETE` | `mistral-large` | Text rating + aspect JSON extraction | One-shot |
| `CORTEX.COMPLETE` | `mistral-large2` | Issue summarisation + AI report | Structured instruction |

---

## 💻 Streamlit Dashboard Tabs

| Tab | Description |
|-----|-------------|
| 📊 **Overview** | 4 KPI cards, top-15 airline bar chart, rating distribution, seat class donut, traveller heatmap |
| 💬 **Sentiment** | Top/bottom airline sentiment ranking, label donut, sentiment vs rating scatter, trend over time |
| 🎯 **Aspects** | Structured aspect heatmap (7 categories × airlines), per-airline radar chart, LLM sentiment heatmap |
| ⚔️ **Compare** | Side-by-side structured scores, LLM sentiment %, radar overlay, KPI delta row for any two airlines |
| ⚠️ **Issues** | Worst airlines bar chart, LLM issue summaries, negative mention rate heatmap |
| 🔍 **Reviews** | Live review explorer — filter by airline, sentiment, limit — per-review LLM classification cards |
| 📝 **AI Report** | On-demand Cortex report — 3 style options, adjustable review count, download as `.txt` |

---

## ⚙️ Key Engineering Decisions

### Medallion Architecture
Four schema layers (`raw` → `harmonized` → `analytics` → `cortex_output`) keep ingestion, transformation, AI enrichment, and analytics consumption completely separated. Updating a transformation only touches one layer; no re-ingestion required.

### CTE-Based LLM Batching
Each `CORTEX.COMPLETE` call is made **exactly once per row** via CTE chains. Naive implementation would fire 3 LLM calls per row; the CTE pattern reduces this to 1, cutting token cost by ~66%.

### Model Tiering by Task Complexity
- `snowflake-arctic` → simple binary classification (cheaper, faster)
- `mistral-large` → structured JSON extraction (one-shot)
- `mistral-large2` → long-form summarisation (best instruction following)

### One-Shot Prompt Engineering
Zero-shot prompting produced inconsistent JSON formats (~60% parse success). Adding a worked example to the prompt (one-shot) achieved near-zero parse failure rate. Documented inline in notebook cells.

### Defensive SQL Throughout
`TRY_TO_DATE`, `TRY_PARSE_JSON`, `NULLIF`, `COALESCE` prevent silent failures. Phased persistent tables mean any failure is isolated to one phase — re-run only that phase, not the entire pipeline.

### Date Parsing Fix
The raw date format (`"11th November 2019"`) required two steps:
1. `REGEXP_REPLACE` with `\\1` backreference to strip ordinal suffixes
2. `LPAD` to zero-pad single-digit days before `TRY_TO_DATE('DD MMMM YYYY')`

---

## 🚀 How to Run

### Prerequisites
- Snowflake account with Cortex LLM functions enabled
- [Check supported regions](https://docs.snowflake.com/user-guide/snowflake-cortex/llm-functions#availability)
- Python 3.11+ (for local development only)

### Step 1 — Upload the dataset

**SnowSQL CLI:**
```bash
snowsql -a YOUR_ACCOUNT -u YOUR_USER
PUT file:///path/to/data/Airline_review.csv @airline_reviews_db.public.airline_stage;
```

**Snowsight UI:**
`Data` → `Add Data` → `Load files into a Stage` → select `airline_stage`

### Step 2 — Run the SQL pipeline

Open a Snowflake SQL Worksheet and run:
```sql
-- Phase 0–6: full pipeline
-- File: sql/01_setup.sql
```

Then run the date parsing fix:
```sql
-- File: sql/02_fix_date_parsing.sql
```

> 💡 **Cost tip:** Add `LIMIT 500` to all `CREATE TABLE AS SELECT` statements during development. Remove for the full run.

### Step 3 — Import the Snowflake Notebook (optional)

1. Snowsight → `Projects` → `Notebooks` → `Import .ipynb`
2. Select `notebook/airline_review_cortex_notebook.ipynb`
3. Database: `airline_reviews_db` | Schema: `analytics` | Warehouse: `airline_ds_wh`
4. Packages: `snowflake-snowpark-python`, `matplotlib`, `seaborn`
5. Click **Run All**

### Step 4 — Deploy the Streamlit App

1. Snowsight → `Projects` → `Streamlit` → `+ Streamlit App`
2. Name: `Airline Review Intelligence`
3. Database: `airline_reviews_db` | Schema: `analytics` | Warehouse: `airline_ds_wh`
4. Packages: `plotly`, `snowflake-snowpark-python`

   > ⚠️ Do **NOT** add `snowflake-ml-python` or `pandas` manually — causes dependency conflict

5. Paste contents of `streamlit/airline_streamlit_app.py` → click **Run**

### Step 5 — Validate the pipeline

```sql
-- Run in a Snowflake Worksheet
SELECT 'raw'              AS layer, COUNT(*) AS rows FROM airline_reviews_db.raw.airline_reviews_raw
UNION ALL
SELECT 'harmonized',       COUNT(*) FROM airline_reviews_db.harmonized.airline_reviews_v
UNION ALL
SELECT 'translated',       COUNT(*) FROM airline_reviews_db.cortex_output.reviews_translated
UNION ALL
SELECT 'sentiment',        COUNT(*) FROM airline_reviews_db.cortex_output.reviews_sentiment
UNION ALL
SELECT 'rated',            COUNT(*) FROM airline_reviews_db.cortex_output.reviews_rated
UNION ALL
SELECT 'aspect_sentiment', COUNT(*) FROM airline_reviews_db.cortex_output.reviews_aspect_sentiment
UNION ALL
SELECT 'issue_summaries',  COUNT(*) FROM airline_reviews_db.cortex_output.airline_issue_summary;
```

---

## 📁 Repository Structure

```
airline-review-intelligence/
│
├── README.md                          ← This file
├── LICENSE                            ← MIT License
├── CONTRIBUTING.md                    ← How to contribute or adapt
├── .gitignore                         ← Excludes credentials and temp files
│
├── sql/
│   ├── 01_setup.sql                   ← Full 6-phase pipeline (740 lines)
│   └── 02_fix_date_parsing.sql        ← Date parsing patch for harmonized view
│
├── notebook/
│   └── airline_review_cortex_notebook.ipynb   ← 31-cell Snowflake Notebook
│
├── streamlit/
│   └── airline_streamlit_app.py       ← 7-tab Streamlit in Snowflake app
│
├── data/
│   └── Airline_review.csv             ← Source dataset (23,617 reviews)
│
└── docs/
    └── architecture.png               ← Architecture diagram (add screenshot)
```

---

## 📊 Dataset

**Source:** [Airline Reviews — Kaggle](https://www.kaggle.com/datasets/juhibhojani/airline-reviews)

| Field | Description |
|-------|-------------|
| `airline_name` | Carrier name (50+ airlines) |
| `overall_rating` | 1–10 numeric rating |
| `review` | Free-text review (multilingual) |
| `seat_type` | Economy / Business / First / Premium Economy |
| `type_of_traveller` | Solo Leisure / Couple / Family / Business |
| `route` | Origin–Destination route |
| `seat_comfort` | 1–5 structured score |
| `cabin_staff_service` | 1–5 structured score |
| `food_and_beverages` | 1–5 structured score |
| `ground_service` | 1–5 structured score |
| `inflight_entertainment` | 1–5 structured score |
| `wifi_and_connectivity` | 1–5 structured score |
| `value_for_money` | 1–5 structured score |
| `recommended` | yes / no |

---

## 🔁 Domain Adaptability

The pipeline is **domain-agnostic**. Swap the dataset and update the aspect categories in the Phase 5a prompt to apply this to:

| Domain | Airline column maps to | Aspect categories |
|--------|----------------------|-------------------|
| Hotels | Property name | Cleanliness, check-in, breakfast, location, staff, Wi-Fi |
| Insurance | Insurer name | Claims speed, agent empathy, settlement fairness, digital portal |
| Healthcare | Hospital name | Doctor communication, wait time, cleanliness, billing, discharge |
| E-commerce | Product name | Quality, packaging, delivery, sizing, value, returns |
| HR / Glassdoor | Company name | Management, culture, growth, compensation, work-life balance |

---

## 🛡️ Cost Management

| Action | Command |
|--------|---------|
| Suspend warehouse | `ALTER WAREHOUSE airline_ds_wh SUSPEND;` |
| Set auto-suspend | `ALTER WAREHOUSE airline_ds_wh SET AUTO_SUSPEND = 60;` |
| Disable auto-resume | `ALTER WAREHOUSE airline_ds_wh SET AUTO_RESUME = FALSE;` |
| Check usage | `SELECT * FROM snowflake.account_usage.metering_daily_history;` |

> ⚠️ The Cortex LLM phases (especially `mistral-large` and `mistral-large2`) consume significant credits. Always test with `LIMIT 500` first.

---

## 📜 License

MIT — free to use, adapt, and build on. See [LICENSE](LICENSE).

---

## 🙋 Author

Built by **[Your Name]** as a senior-level portfolio project demonstrating end-to-end data engineering, analytics engineering, and AI/NLP pipeline skills on the Snowflake ecosystem.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?logo=linkedin&logoColor=white)](https://linkedin.com/in/YOUR_LINKEDIN)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?logo=github&logoColor=white)](https://github.com/YOUR_USERNAME)
