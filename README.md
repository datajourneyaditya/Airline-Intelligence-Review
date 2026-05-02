# Dataset

## Airline_review.csv

**Source:** [Airline Reviews — Kaggle](https://www.kaggle.com/datasets/juhibhojani/airline-reviews)

**Size:** ~23,617 rows × 20 columns

**How to get it:**
1. Download from Kaggle (free account required)
2. Or use the CSV included in this repo directly

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `row_id` | INTEGER | Unique row identifier |
| `airline_name` | VARCHAR | Airline name (50+ airlines) |
| `overall_rating` | FLOAT | Overall score 1–10 |
| `review_title` | VARCHAR | Short review title |
| `review_date` | VARCHAR | Date string e.g. "11th November 2019" |
| `verified` | VARCHAR | Trip verified flag |
| `review` | VARCHAR | Full free-text review |
| `aircraft` | VARCHAR | Aircraft type |
| `type_of_traveller` | VARCHAR | Solo Leisure / Couple / Family / Business |
| `seat_type` | VARCHAR | Economy / Business / First / Premium Economy |
| `route` | VARCHAR | Origin–Destination |
| `date_flown` | VARCHAR | Month/Year of travel |
| `seat_comfort` | FLOAT | 1–5 structured score |
| `cabin_staff_service` | FLOAT | 1–5 structured score |
| `food_and_beverages` | FLOAT | 1–5 structured score |
| `ground_service` | FLOAT | 1–5 structured score |
| `inflight_entertainment` | FLOAT | 1–5 structured score |
| `wifi_and_connectivity` | FLOAT | 1–5 structured score |
| `value_for_money` | FLOAT | 1–5 structured score |
| `recommended` | VARCHAR | yes / no |

## Notes

- `review_date` is stored as a raw string and parsed in Phase 2 of the pipeline
- Aspect score columns (seat_comfort etc.) are nullable — many reviews only rate a subset
- Reviews are multilingual — Phase 3 handles translation to English
