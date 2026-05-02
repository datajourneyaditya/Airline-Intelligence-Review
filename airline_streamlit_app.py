# ============================================================
# AIRLINE REVIEW INTELLIGENCE PLATFORM
# Streamlit in Snowflake App  — v2 (no snowflake-ml-python)
# ============================================================
# HOW TO DEPLOY:
#   1. Snowsight → Projects → Streamlit → + Streamlit App
#   2. Name      : Airline Review Intelligence
#   3. Database  : airline_reviews_db   Schema: analytics
#   4. Warehouse : airline_ds_wh
#   5. Packages  : plotly   snowflake-snowpark-python
#      !! Do NOT add snowflake-ml-python — causes pandas conflict !!
#   6. Paste this file into the editor and click Run
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import warnings
warnings.filterwarnings("ignore")

from snowflake.snowpark.context import get_active_session

# ── Cortex helper — pure SQL, zero extra packages ─────────────────────────────
def cortex_complete(model: str, prompt: str, _session) -> str:
    """Call SNOWFLAKE.CORTEX.COMPLETE via SQL — no snowflake-ml-python needed."""
    safe = prompt.replace("'", "''")
    rows = _session.sql(
        f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}', '{safe}') AS out"
    ).collect()
    return rows[0]["OUT"] if rows else ""


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Airline Review Intelligence",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Palette ───────────────────────────────────────────────────────────────────
PALETTE   = ["#1D9E75", "#E24B4A", "#3B8BD4", "#EF9F27", "#7F77DD", "#D85A30", "#639922"]
COLOR_POS = "#1D9E75"
COLOR_NEG = "#E24B4A"
COLOR_NEU = "#3B8BD4"

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header{font-size:2rem;font-weight:700;color:#1D9E75;margin-bottom:0}
    .sub-header{font-size:0.9rem;color:#888;margin-top:0;margin-bottom:1.5rem}
    .kpi-box{background:#f8f9fa;border-radius:10px;padding:1rem 1.2rem;
             border-left:4px solid #1D9E75;margin-bottom:0.5rem}
    .kpi-value{font-size:1.8rem;font-weight:700;color:#1a1a1a;line-height:1.1}
    .kpi-label{font-size:0.8rem;color:#666;margin-top:2px}
    .kpi-delta-pos{font-size:0.8rem;color:#1D9E75;font-weight:600}
    .kpi-delta-neg{font-size:0.8rem;color:#E24B4A;font-weight:600}
    .section-title{font-size:1rem;font-weight:600;color:#333;
                   border-bottom:1px solid #eee;padding-bottom:6px;margin-bottom:12px}
    .issue-card{background:#fff;border:1px solid #eee;border-radius:8px;
                padding:1rem;margin-bottom:0.75rem;border-left:3px solid #E24B4A}
    .report-box{background:#f8f9fa;border:1px solid #e0e0e0;border-radius:8px;
                padding:1.2rem;font-size:0.88rem;line-height:1.7;color:#333}
    .badge-pos{background:#d4edda;color:#155724;padding:2px 10px;
               border-radius:12px;font-size:0.75rem;font-weight:600}
    .badge-neg{background:#f8d7da;color:#721c24;padding:2px 10px;
               border-radius:12px;font-size:0.75rem;font-weight:600}
    .badge-neu{background:#d1ecf1;color:#0c5460;padding:2px 10px;
               border-radius:12px;font-size:0.75rem;font-weight:600}
    div[data-testid="stSidebarContent"]{background:#fafafa}
</style>
""", unsafe_allow_html=True)

# ── Session ───────────────────────────────────────────────────────────────────
@st.cache_resource
def get_session():
    return get_active_session()

session = get_session()

# ── Data loaders ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_kpis():
    return session.sql("""
        SELECT
            airline_name,
            total_reviews,
            avg_rating,
            avg_sentiment,
            recommended_pct,
            avg_seat_comfort,
            avg_cabin_staff,
            avg_food,
            COALESCE(avg_ground_service, avg_ground, 0) AS avg_ground_service,
            COALESCE(avg_ife, 0)                        AS avg_ife,
            COALESCE(avg_wifi, 0)                       AS avg_wifi,
            avg_value
        FROM airline_reviews_db.analytics.v_airline_kpis
        WHERE total_reviews >= 5
        ORDER BY total_reviews DESC
    """).to_pandas()

@st.cache_data(ttl=300)
def load_sentiment_time():
    return session.sql("""
        SELECT
            airline_name,
            CAST(review_month AS DATE)              AS review_month,
            review_count,
            avg_sentiment,
            avg_rating
        FROM airline_reviews_db.analytics.v_sentiment_over_time
        WHERE review_month IS NOT NULL
        ORDER BY airline_name, review_month
    """).to_pandas()

@st.cache_data(ttl=300)
def load_aspects_class():
    return session.sql("""
        SELECT * FROM airline_reviews_db.analytics.v_aspects_by_class
        WHERE review_count >= 5
    """).to_pandas()

@st.cache_data(ttl=300)
def load_llm_aspects():
    return session.sql("""
        SELECT * FROM airline_reviews_db.analytics.v_llm_aspect_scores
        WHERE total_mentions >= 5
    """).to_pandas()

@st.cache_data(ttl=300)
def load_issues():
    return session.sql("""
        SELECT * FROM airline_reviews_db.analytics.v_airline_issues
        ORDER BY avg_sentiment ASC
    """).to_pandas()

@st.cache_data(ttl=300)
def load_aspect_flat():
    return session.sql("""
        SELECT airline_name, aspect_category, aspect_sentiment, COUNT(*) AS cnt
        FROM airline_reviews_db.analytics.aspect_flat_v
        WHERE aspect_category IS NOT NULL
        GROUP BY airline_name, aspect_category, aspect_sentiment
    """).to_pandas()

@st.cache_data(ttl=300)
def load_sample_reviews(airline, sentiment_filter, limit=20):
    sentiment_clause = ""
    if sentiment_filter == "Positive":
        sentiment_clause = "AND sentiment_label = 'positive'"
    elif sentiment_filter == "Negative":
        sentiment_clause = "AND sentiment_label = 'negative'"
    airline_safe = airline.replace("'", "''")
    return session.sql(f"""
        SELECT review_id, overall_rating, sentiment_score, sentiment_label,
               seat_type, traveller_type, route, rating_llm, recommend_llm,
               LEFT(review_english, 300) AS review_snippet
        FROM airline_reviews_db.cortex_output.reviews_rated
        WHERE airline_name = '{airline_safe}' {sentiment_clause}
        ORDER BY ABS(sentiment_score) DESC
        LIMIT {limit}
    """).to_pandas()

@st.cache_data(ttl=300)
def load_worst_reviews_for_report(airline, limit=100):
    airline_safe = airline.replace("'", "''")
    rows = session.sql(f"""
        SELECT LISTAGG(review_english, ' | ') WITHIN GROUP (ORDER BY sentiment_score ASC) AS agg
        FROM (
            SELECT review_english, sentiment_score
            FROM airline_reviews_db.cortex_output.reviews_rated
            WHERE airline_name = '{airline_safe}'
            ORDER BY sentiment_score ASC
            LIMIT {limit}
        )
    """).collect()
    return rows[0]["AGG"] if rows else ""


# ── Sidebar ───────────────────────────────────────────────────────────────────
df_kpis = load_kpis()
airline_list = sorted(df_kpis["AIRLINE_NAME"].tolist())

with st.sidebar:
    st.markdown("## ✈️ Airline Review Intelligence")
    st.markdown("*Powered by Snowflake Cortex*")
    st.divider()

    st.markdown("### 🔍 Filters")
    selected_airline = st.selectbox("Airline", ["All airlines"] + airline_list)
    selected_seat = st.selectbox(
        "Seat class",
        ["All classes", "Economy Class", "Business Class", "First Class", "Premium Economy"]
    )
    selected_traveller = st.selectbox(
        "Traveller type",
        ["All types", "Solo Leisure", "Couple Leisure", "Family Leisure", "Business"]
    )
    min_reviews = st.slider("Min reviews per airline", 5, 200, 20, step=5)

    st.divider()
    st.markdown("### ⚔️ Competitor Compare")
    airline_a = st.selectbox(
        "Airline A", airline_list,
        index=airline_list.index("British Airways") if "British Airways" in airline_list else 0
    )
    airline_b = st.selectbox(
        "Airline B", airline_list,
        index=airline_list.index("Emirates") if "Emirates" in airline_list else min(1, len(airline_list)-1)
    )
    if st.button("Compare airlines →", use_container_width=True):
        st.session_state["run_compare"] = True
    if st.button("Clear comparison", use_container_width=True):
        st.session_state["run_compare"] = False
    run_compare = st.session_state.get("run_compare", False)
    if run_compare:
        st.success(f"Comparing: {airline_a} vs {airline_b}")

    st.divider()
    total_reviews = int(df_kpis["TOTAL_REVIEWS"].sum())
    total_airlines = len(df_kpis)
    st.markdown(f"**{total_reviews:,}** reviews · **{total_airlines}** airlines")


# ── Filtered data ─────────────────────────────────────────────────────────────
df_filtered = df_kpis[df_kpis["TOTAL_REVIEWS"] >= min_reviews].copy()
df_selected = (
    df_filtered[df_filtered["AIRLINE_NAME"] == selected_airline]
    if selected_airline != "All airlines"
    else df_filtered
)


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-header">✈️ Airline Review Intelligence</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Customer experience analytics · Snowflake Cortex NLP pipeline</p>',
    unsafe_allow_html=True
)


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_overview, tab_sentiment, tab_aspects, tab_compare, tab_issues, tab_reviews, tab_report = st.tabs([
    "📊 Overview", "💬 Sentiment", "🎯 Aspects", "⚔️ Compare", "⚠️ Issues", "🔍 Reviews", "📝 AI Report"
])


# ════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════
with tab_overview:
    kpi_df = df_selected if len(df_selected) else df_filtered
    avg_rating    = round(float(kpi_df["AVG_RATING"].mean()), 2)    if len(kpi_df) else 0.0
    avg_sentiment = round(float(kpi_df["AVG_SENTIMENT"].mean()), 3) if len(kpi_df) else 0.0
    rec_pct       = round(float(kpi_df["RECOMMENDED_PCT"].mean()), 1) if len(kpi_df) and "RECOMMENDED_PCT" in kpi_df.columns else 0.0
    n_reviews     = int(kpi_df["TOTAL_REVIEWS"].sum()) if len(kpi_df) else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="kpi-box">
            <div class="kpi-value">{avg_rating}</div>
            <div class="kpi-label">Avg overall rating (/ 10)</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        delta_cls = "kpi-delta-pos" if avg_sentiment >= 0 else "kpi-delta-neg"
        delta_lbl = "positive lean" if avg_sentiment >= 0.2 else ("negative lean" if avg_sentiment <= -0.2 else "neutral")
        st.markdown(f"""<div class="kpi-box">
            <div class="kpi-value">{avg_sentiment:+.3f}</div>
            <div class="kpi-label">Avg Cortex sentiment score</div>
            <div class="{delta_cls}">{delta_lbl}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="kpi-box">
            <div class="kpi-value">{rec_pct}%</div>
            <div class="kpi-label">Would recommend</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="kpi-box">
            <div class="kpi-value">{n_reviews:,}</div>
            <div class="kpi-label">Reviews analysed</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_left, col_right = st.columns([1.4, 1])

    with col_left:
        st.markdown('<p class="section-title">Top airlines by average rating</p>', unsafe_allow_html=True)
        top_n = df_filtered.nlargest(15, "AVG_RATING")
        fig_bar = px.bar(
            top_n.sort_values("AVG_RATING"),
            x="AVG_RATING", y="AIRLINE_NAME", orientation="h",
            color="AVG_RATING",
            color_continuous_scale=["#E24B4A", "#EF9F27", "#1D9E75"],
            range_color=[1, 10],
            text="AVG_RATING",
            labels={"AVG_RATING": "Avg rating", "AIRLINE_NAME": ""},
        )
        fig_bar.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig_bar.update_layout(
            height=420, margin=dict(l=0, r=40, t=10, b=10),
            coloraxis_showscale=False,
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis=dict(range=[0, 11], showgrid=True, gridcolor="#f0f0f0"),
            yaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_right:
        st.markdown('<p class="section-title">Rating distribution</p>', unsafe_allow_html=True)
        df_dist_all = session.sql("""
            SELECT overall_rating, COUNT(*) AS cnt
            FROM airline_reviews_db.harmonized.airline_reviews_v
            GROUP BY overall_rating ORDER BY overall_rating
        """).to_pandas()
        fig_dist = px.bar(
            df_dist_all, x="OVERALL_RATING", y="CNT",
            color="OVERALL_RATING",
            color_continuous_scale=["#E24B4A", "#EF9F27", "#1D9E75"],
            range_color=[1, 10],
            labels={"OVERALL_RATING": "Rating", "CNT": "Reviews"},
        )
        fig_dist.update_layout(
            height=200, margin=dict(l=0, r=10, t=10, b=10),
            coloraxis_showscale=False,
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_dist, use_container_width=True)

        st.markdown('<p class="section-title">Reviews by seat class</p>', unsafe_allow_html=True)
        df_seat = session.sql("""
            SELECT seat_type, COUNT(*) AS cnt
            FROM airline_reviews_db.harmonized.airline_reviews_v
            WHERE seat_type IS NOT NULL GROUP BY seat_type ORDER BY cnt DESC
        """).to_pandas()
        fig_pie = px.pie(
            df_seat, names="SEAT_TYPE", values="CNT",
            color_discrete_sequence=PALETTE, hole=0.45,
        )
        fig_pie.update_layout(
            height=200, margin=dict(l=0, r=0, t=10, b=10),
            legend=dict(font=dict(size=10))
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown('<p class="section-title">Avg rating by traveller type & seat class</p>', unsafe_allow_html=True)
    df_traveller = session.sql("""
        SELECT traveller_type, seat_type,
               ROUND(AVG(overall_rating), 2) AS avg_rating,
               COUNT(*) AS review_count
        FROM airline_reviews_db.harmonized.airline_reviews_v
        WHERE traveller_type IS NOT NULL AND seat_type IS NOT NULL
        GROUP BY traveller_type, seat_type HAVING review_count >= 10
    """).to_pandas()
    fig_heat = px.density_heatmap(
        df_traveller, x="SEAT_TYPE", y="TRAVELLER_TYPE", z="AVG_RATING",
        color_continuous_scale="RdYlGn", range_color=[1, 10], text_auto=".1f",
        labels={"SEAT_TYPE": "Seat class", "TRAVELLER_TYPE": "Traveller type", "AVG_RATING": "Avg rating"},
    )
    fig_heat.update_layout(
        height=260, margin=dict(l=0, r=0, t=10, b=10),
        plot_bgcolor="white", paper_bgcolor="white",
    )
    st.plotly_chart(fig_heat, use_container_width=True)


# ════════════════════════════════════════════════════════════════
# TAB 2 — SENTIMENT
# ════════════════════════════════════════════════════════════════
with tab_sentiment:
    df_sent_time = load_sentiment_time()
    df_sent_time["REVIEW_MONTH"] = pd.to_datetime(df_sent_time["REVIEW_MONTH"], errors="coerce")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<p class="section-title">Top & bottom 10 airlines by sentiment</p>', unsafe_allow_html=True)
        df_sent_rank = df_filtered.sort_values("AVG_SENTIMENT", ascending=False)
        top10    = df_sent_rank.head(10).assign(GROUP="Top 10")
        bottom10 = df_sent_rank.tail(10).assign(GROUP="Bottom 10")
        df_combined = pd.concat([top10, bottom10])
        fig_sent = px.bar(
            df_combined.sort_values("AVG_SENTIMENT"),
            x="AVG_SENTIMENT", y="AIRLINE_NAME",
            color="GROUP",
            color_discrete_map={"Top 10": COLOR_POS, "Bottom 10": COLOR_NEG},
            orientation="h",
            labels={"AVG_SENTIMENT": "Avg sentiment (–1 to +1)", "AIRLINE_NAME": ""},
        )
        fig_sent.add_vline(x=0, line_dash="dash", line_color="gray", line_width=1)
        fig_sent.update_layout(
            height=450, margin=dict(l=0, r=20, t=10, b=10),
            plot_bgcolor="white", paper_bgcolor="white",
            legend_title_text="",
            xaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        )
        st.plotly_chart(fig_sent, use_container_width=True)

    with col2:
        st.markdown('<p class="section-title">Sentiment label distribution</p>', unsafe_allow_html=True)
        df_label_dist = session.sql("""
            SELECT sentiment_label, COUNT(*) AS cnt
            FROM airline_reviews_db.cortex_output.reviews_sentiment
            GROUP BY sentiment_label
        """).to_pandas()
        color_map = {"positive": COLOR_POS, "negative": COLOR_NEG, "neutral": COLOR_NEU}
        fig_donut = px.pie(
            df_label_dist, names="SENTIMENT_LABEL", values="CNT",
            color="SENTIMENT_LABEL", color_discrete_map=color_map, hole=0.5,
        )
        fig_donut.update_layout(
            height=220, margin=dict(l=0, r=0, t=10, b=10),
            legend=dict(font=dict(size=11))
        )
        st.plotly_chart(fig_donut, use_container_width=True)

        st.markdown('<p class="section-title">Sentiment vs numeric rating</p>', unsafe_allow_html=True)
        fig_scatter = px.scatter(
            df_filtered,
            x="AVG_SENTIMENT", y="AVG_RATING",
            size="TOTAL_REVIEWS",
            color="AVG_SENTIMENT",
            color_continuous_scale=["#E24B4A", "#EF9F27", "#1D9E75"],
            hover_name="AIRLINE_NAME",
            labels={"AVG_SENTIMENT": "Avg Cortex sentiment", "AVG_RATING": "Avg numeric rating"},
            size_max=30,
        )
        fig_scatter.update_layout(
            height=220, margin=dict(l=0, r=0, t=10, b=10),
            coloraxis_showscale=False,
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown('<p class="section-title">Sentiment trend over time</p>', unsafe_allow_html=True)

    # ── Diagnose the time data before rendering ───────────────────────────────
    _has_dates = (
        len(df_sent_time) > 0
        and "REVIEW_MONTH" in df_sent_time.columns
        and df_sent_time["REVIEW_MONTH"].notna().sum() > 0
    )

    if not _has_dates:
        # Fallback: build trend by year directly from the ratings table
        st.caption("Monthly date data not available in the view — showing yearly trend instead.")
        df_sent_time = session.sql("""
            SELECT
                airline_name,
                TO_DATE(CONCAT(YEAR(review_date)::VARCHAR, '-01-01')) AS review_month,
                COUNT(*)                         AS review_count,
                ROUND(AVG(sentiment_score), 3)   AS avg_sentiment,
                ROUND(AVG(overall_rating), 2)    AS avg_rating
            FROM airline_reviews_db.cortex_output.reviews_rated
            WHERE review_date IS NOT NULL
            GROUP BY airline_name, YEAR(review_date)
            ORDER BY airline_name, review_month
        """).to_pandas()
        df_sent_time["REVIEW_MONTH"] = pd.to_datetime(df_sent_time["REVIEW_MONTH"], errors="coerce")
    else:
        df_sent_time["REVIEW_MONTH"] = pd.to_datetime(df_sent_time["REVIEW_MONTH"], errors="coerce")
        df_sent_time = df_sent_time.dropna(subset=["REVIEW_MONTH"])

    # Show row count to help user understand data availability
    _valid_rows = df_sent_time["REVIEW_MONTH"].notna().sum()
    st.caption(f"Data points available: {_valid_rows:,} across {df_sent_time['AIRLINE_NAME'].nunique()} airlines")

    airlines_for_trend = st.multiselect(
        "Select airlines to compare",
        options=airline_list,
        default=airline_list[:5] if len(airline_list) >= 5 else airline_list,
    )

    if airlines_for_trend:
        df_trend_filtered = df_sent_time[
            df_sent_time["AIRLINE_NAME"].isin(airlines_for_trend)
        ].dropna(subset=["REVIEW_MONTH"]).sort_values("REVIEW_MONTH")

        if len(df_trend_filtered) == 0:
            st.info(
                "No dated sentiment data found for the selected airlines. "
                "This usually means the `review_date` column is NULL in most rows — "
                "check that Phase 2 (harmonized view date parsing) ran successfully."
            )
        else:
            # Drop airlines with only 1 data point (can't draw a line)
            counts = df_trend_filtered.groupby("AIRLINE_NAME")["REVIEW_MONTH"].count()
            valid_airlines = counts[counts >= 2].index
            df_trend_filtered = df_trend_filtered[df_trend_filtered["AIRLINE_NAME"].isin(valid_airlines)]

            if len(df_trend_filtered) == 0:
                st.info("Each selected airline has only one data point — not enough to draw a trend line. Try selecting airlines with more reviews.")
            else:
                fig_line = px.line(
                    df_trend_filtered,
                    x="REVIEW_MONTH", y="AVG_SENTIMENT",
                    color="AIRLINE_NAME",
                    color_discrete_sequence=PALETTE,
                    markers=True,
                    labels={"REVIEW_MONTH": "Date", "AVG_SENTIMENT": "Avg sentiment", "AIRLINE_NAME": "Airline"},
                )
                fig_line.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
                fig_line.update_traces(marker=dict(size=5))
                fig_line.update_layout(
                    height=340, margin=dict(l=0, r=0, t=10, b=10),
                    plot_bgcolor="white", paper_bgcolor="white",
                    xaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
                    yaxis=dict(showgrid=True, gridcolor="#f0f0f0", range=[-1.1, 1.1]),
                    legend=dict(font=dict(size=10)),
                )
                st.plotly_chart(fig_line, use_container_width=True)


# ════════════════════════════════════════════════════════════════
# TAB 3 — ASPECTS
# ════════════════════════════════════════════════════════════════
with tab_aspects:
    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.markdown('<p class="section-title">Structured aspect scores by airline (avg 1–5)</p>', unsafe_allow_html=True)
        # Build aspect map using only columns that actually exist in the view
        _all_aspect_cols = {
            "AVG_SEAT_COMFORT":   "Seat comfort",
            "AVG_CABIN_STAFF":    "Cabin staff",
            "AVG_FOOD":           "Food & bev",
            "AVG_GROUND_SERVICE": "Ground service",
            "AVG_IFE":            "IFE",
            "AVG_WIFI":           "Wi-Fi",
            "AVG_VALUE":          "Value",
        }
        aspect_cols = {k: v for k, v in _all_aspect_cols.items() if k in df_filtered.columns}
        df_asp = df_filtered[["AIRLINE_NAME", "TOTAL_REVIEWS"] + list(aspect_cols.keys())].copy()
        df_asp = df_asp[df_asp["TOTAL_REVIEWS"] >= min_reviews].nlargest(15, "TOTAL_REVIEWS")
        df_asp_melt = df_asp.melt(
            id_vars=["AIRLINE_NAME"], value_vars=list(aspect_cols.keys()),
            var_name="aspect_raw", value_name="score",
        )
        df_asp_melt["Aspect"] = df_asp_melt["aspect_raw"].map(aspect_cols)
        pivot_asp = df_asp_melt.pivot_table(index="AIRLINE_NAME", columns="Aspect", values="score")
        fig_hmap = px.imshow(
            pivot_asp, color_continuous_scale="RdYlGn",
            range_color=[1, 5], text_auto=".1f", aspect="auto",
            labels={"color": "Avg score"},
        )
        fig_hmap.update_layout(
            height=420, margin=dict(l=0, r=0, t=10, b=10),
            coloraxis_colorbar=dict(len=0.7, thickness=12),
        )
        st.plotly_chart(fig_hmap, use_container_width=True)

    with col2:
        st.markdown('<p class="section-title">Radar — aspect profile</p>', unsafe_allow_html=True)
        radar_airline = st.selectbox("Select airline for radar", airline_list, key="radar_airline")
        df_radar_row = df_kpis[df_kpis["AIRLINE_NAME"] == radar_airline]
        if len(df_radar_row):
            row = df_radar_row.iloc[0]
            _radar_map = [
                ("AVG_SEAT_COMFORT",   "Seat comfort"),
                ("AVG_CABIN_STAFF",    "Cabin staff"),
                ("AVG_FOOD",           "Food & bev"),
                ("AVG_GROUND_SERVICE", "Ground svc"),
                ("AVG_IFE",            "IFE"),
                ("AVG_WIFI",           "Wi-Fi"),
                ("AVG_VALUE",          "Value"),
            ]
            r_vals   = [float(row.get(k, 0) or 0) for k, _ in _radar_map]
            r_labels = [label for _, label in _radar_map]
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=r_vals + [r_vals[0]],
                theta=r_labels + [r_labels[0]],
                fill="toself",
                fillcolor="rgba(29,158,117,0.15)",
                line=dict(color=COLOR_POS, width=2),
                name=radar_airline,
            ))
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 5], tickfont=dict(size=9)),
                    angularaxis=dict(tickfont=dict(size=10)),
                ),
                showlegend=False,
                height=340, margin=dict(l=30, r=30, t=30, b=30),
            )
            st.plotly_chart(fig_radar, use_container_width=True)
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Avg rating",  f"{float(row.get('AVG_RATING', 0) or 0):.1f} / 10")
            mc2.metric("Sentiment",   f"{float(row.get('AVG_SENTIMENT', 0) or 0):+.3f}")
            mc3.metric("Recommend",   f"{float(row.get('RECOMMENDED_PCT', 0) or 0):.0f}%")

    st.markdown('<p class="section-title">LLM-derived aspect sentiment — net score per airline</p>', unsafe_allow_html=True)
    try:
        df_llm_asp = load_llm_aspects()
        if len(df_llm_asp):
            top_al = df_llm_asp.groupby("AIRLINE_NAME")["TOTAL_MENTIONS"].sum().nlargest(14).index
            pivot_llm = df_llm_asp[df_llm_asp["AIRLINE_NAME"].isin(top_al)].pivot_table(
                index="AIRLINE_NAME", columns="ASPECT_CATEGORY",
                values="NET_SENTIMENT_SCORE", aggfunc="mean",
            )
            fig_llm_hmap = px.imshow(
                pivot_llm, color_continuous_scale="RdYlGn",
                range_color=[-1, 1], text_auto=".2f", aspect="auto",
                labels={"color": "Net sentiment"},
            )
            fig_llm_hmap.update_layout(
                height=380, margin=dict(l=0, r=0, t=10, b=10),
                coloraxis_colorbar=dict(len=0.7, thickness=12),
            )
            st.plotly_chart(fig_llm_hmap, use_container_width=True)
    except Exception as e:
        st.info(f"LLM aspect view not yet available — run Phase 5a in the notebook first. ({e})")





# ════════════════════════════════════════════════════════════════
# TAB 4 — COMPETITOR COMPARE
# ════════════════════════════════════════════════════════════════
with tab_compare:
    if not run_compare:
        st.info(
            "Select **Airline A** and **Airline B** in the sidebar, "
            "then click **Compare airlines →** to run the comparison."
        )
    else:
        st.markdown(
            f'<p class="section-title">Comparing: {airline_a} vs {airline_b}</p>',
            unsafe_allow_html=True
        )

        # ── Structured numeric scores side-by-side ────────────────────────
        st.markdown("#### Structured aspect scores (avg 1–5)")
        _aspect_pairs = [
            ("AVG_SEAT_COMFORT",   "Seat comfort"),
            ("AVG_CABIN_STAFF",    "Cabin staff"),
            ("AVG_FOOD",           "Food & bev"),
            ("AVG_GROUND_SERVICE", "Ground service"),
            ("AVG_IFE",            "IFE"),
            ("AVG_WIFI",           "Wi-Fi"),
            ("AVG_VALUE",          "Value"),
        ]
        row_a = df_kpis[df_kpis["AIRLINE_NAME"] == airline_a]
        row_b = df_kpis[df_kpis["AIRLINE_NAME"] == airline_b]

        if len(row_a) and len(row_b):
            ra, rb = row_a.iloc[0], row_b.iloc[0]
            compare_rows = []
            for col, label in _aspect_pairs:
                val_a = float(ra.get(col, 0) or 0)
                val_b = float(rb.get(col, 0) or 0)
                if val_a > 0 or val_b > 0:
                    compare_rows.append({"Aspect": label, airline_a: val_a, airline_b: val_b})

            if compare_rows:
                df_score_comp = pd.DataFrame(compare_rows)
                df_score_melt = df_score_comp.melt(
                    id_vars="Aspect", var_name="Airline", value_name="Score"
                )
                fig_scores = px.bar(
                    df_score_melt.sort_values("Aspect"),
                    x="Score", y="Aspect", color="Airline",
                    color_discrete_map={airline_a: PALETTE[2], airline_b: PALETTE[3]},
                    barmode="group", orientation="h", text="Score",
                    labels={"Score": "Avg score (1–5)", "Aspect": ""},
                )
                fig_scores.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                fig_scores.update_layout(
                    height=360, margin=dict(l=0, r=60, t=10, b=10),
                    plot_bgcolor="white", paper_bgcolor="white",
                    xaxis=dict(range=[0, 6]),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig_scores, use_container_width=True)

            # KPI summary row
            kpi_cols = st.columns(4)
            kpi_data = [
                ("Avg rating",    "AVG_RATING",       "{:.1f}"),
                ("Sentiment",     "AVG_SENTIMENT",     "{:+.3f}"),
                ("Recommend %",   "RECOMMENDED_PCT",   "{:.0f}%"),
                ("Total reviews", "TOTAL_REVIEWS",     "{:,.0f}"),
            ]
            for i, (label, col, fmt) in enumerate(kpi_data):
                va = float(ra.get(col, 0) or 0) if col != "TOTAL_REVIEWS" else int(ra.get(col, 0) or 0)
                vb = float(rb.get(col, 0) or 0) if col != "TOTAL_REVIEWS" else int(rb.get(col, 0) or 0)
                delta = va - vb if col != "TOTAL_REVIEWS" else None
                with kpi_cols[i]:
                    st.markdown(f"**{label}**")
                    d_str = ""
                    if delta is not None:
                        sign = "+" if delta > 0 else ""
                        color = "#1D9E75" if delta > 0 else "#E24B4A"
                        d_str = f'<span style="color:{color};font-size:0.8rem">{sign}{delta:.2f} vs {airline_b}</span>'
                    st.markdown(
                        f'<div style="font-size:1.3rem;font-weight:600">{fmt.format(va)}</div>'
                        f'<div style="font-size:0.8rem;color:#888">{airline_a}</div>'
                        f'<div style="font-size:1.3rem;font-weight:600;margin-top:6px">{fmt.format(vb)}</div>'
                        f'<div style="font-size:0.8rem;color:#888">{airline_b}</div>'
                        f'{d_str}',
                        unsafe_allow_html=True
                    )

        st.markdown("<br>", unsafe_allow_html=True)

        # ── LLM aspect sentiment positive % comparison ────────────────────
        st.markdown("#### LLM-derived aspect sentiment — % positive mentions")
        try:
            df_flat = load_aspect_flat()
            df_comp = df_flat[df_flat["AIRLINE_NAME"].isin([airline_a, airline_b])].copy()
            if len(df_comp):
                df_tot  = df_comp.groupby(["AIRLINE_NAME", "ASPECT_CATEGORY"])["CNT"].sum().reset_index()
                df_tot.columns = ["AIRLINE_NAME", "ASPECT_CATEGORY", "TOTAL"]
                df_pos  = df_comp[df_comp["ASPECT_SENTIMENT"] == "positive"].copy()
                df_pos_m = df_pos.merge(df_tot, on=["AIRLINE_NAME", "ASPECT_CATEGORY"])
                df_pos_m["POS_PCT"] = (df_pos_m["CNT"] / df_pos_m["TOTAL"] * 100).round(1)

                fig_comp = px.bar(
                    df_pos_m.sort_values("ASPECT_CATEGORY"),
                    x="POS_PCT", y="ASPECT_CATEGORY",
                    color="AIRLINE_NAME",
                    color_discrete_map={airline_a: PALETTE[2], airline_b: PALETTE[3]},
                    barmode="group", orientation="h", text="POS_PCT",
                    labels={"POS_PCT": "% Positive mentions", "ASPECT_CATEGORY": "", "AIRLINE_NAME": "Airline"},
                )
                fig_comp.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
                fig_comp.add_vline(x=50, line_dash="dash", line_color="gray", line_width=1)
                fig_comp.update_layout(
                    height=400, margin=dict(l=0, r=70, t=10, b=10),
                    plot_bgcolor="white", paper_bgcolor="white",
                    xaxis=dict(range=[0, 115]),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig_comp, use_container_width=True)
            else:
                st.info("No LLM aspect data found for these airlines. Run Phase 5a in the notebook first.")
        except Exception as e:
            st.info(f"LLM aspect data not yet available ({e})")

        # ── Radar overlay ─────────────────────────────────────────────────
        st.markdown("#### Radar overlay — structured scores")
        if len(row_a) and len(row_b):
            fig_radar_comp = go.Figure()
            for airline_name, row_data, color in [
                (airline_a, ra, PALETTE[2]),
                (airline_b, rb, PALETTE[3]),
            ]:
                vals = [float(row_data.get(c, 0) or 0) for c, _ in _aspect_pairs]
                labels_r = [l for _, l in _aspect_pairs]
                fig_radar_comp.add_trace(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=labels_r + [labels_r[0]],
                    fill="toself",
                    opacity=0.5,
                    line=dict(color=color, width=2),
                    name=airline_name,
                ))
            fig_radar_comp.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 5], tickfont=dict(size=9)),
                    angularaxis=dict(tickfont=dict(size=10)),
                ),
                height=380, margin=dict(l=40, r=40, t=40, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=-0.15),
            )
            st.plotly_chart(fig_radar_comp, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 5 — ISSUES
# ════════════════════════════════════════════════════════════════
with tab_issues:
    col1, col2 = st.columns([1, 1.2])

    with col1:
        st.markdown('<p class="section-title">Most negatively reviewed airlines</p>', unsafe_allow_html=True)
        df_worst = df_filtered.nsmallest(15, "AVG_SENTIMENT")[
            ["AIRLINE_NAME", "AVG_SENTIMENT", "AVG_RATING", "TOTAL_REVIEWS"]
        ]
        fig_worst = px.bar(
            df_worst.sort_values("AVG_SENTIMENT", ascending=False),
            x="AVG_SENTIMENT", y="AIRLINE_NAME", orientation="h",
            color="AVG_SENTIMENT",
            color_continuous_scale=["#E24B4A", "#EF9F27", "#c8e6c9"],
            range_color=[-1, 0.5], text="AVG_SENTIMENT",
            labels={"AVG_SENTIMENT": "Avg sentiment", "AIRLINE_NAME": ""},
        )
        fig_worst.update_traces(texttemplate="%{text:.3f}", textposition="outside")
        fig_worst.add_vline(x=0, line_dash="dash", line_color="gray", line_width=1)
        fig_worst.update_layout(
            height=420, margin=dict(l=0, r=60, t=10, b=10),
            coloraxis_showscale=False,
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_worst, use_container_width=True)

    with col2:
        st.markdown('<p class="section-title">LLM issue summary</p>', unsafe_allow_html=True)
        try:
            df_iss_summary = load_issues()
            if len(df_iss_summary):
                issue_airline = st.selectbox(
                    "Select airline", df_iss_summary["AIRLINE_NAME"].tolist(), key="issue_airline"
                )
                row_iss = df_iss_summary[df_iss_summary["AIRLINE_NAME"] == issue_airline]
                if len(row_iss):
                    r = row_iss.iloc[0]
                    ic1, ic2, ic3 = st.columns(3)
                    ic1.metric("Avg rating",    f"{float(r['AVG_RATING']):.1f}")
                    ic2.metric("Avg sentiment", f"{float(r['AVG_SENTIMENT']):+.3f}")
                    ic3.metric("Reviews used",  f"{int(r['REVIEW_COUNT']):,}")
                    st.markdown(
                        f'<div class="issue-card">{r["ISSUE_SUMMARY"]}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Run Phase 5b in the notebook to generate issue summaries.")
        except Exception as e:
            st.info(f"Issue summaries not yet available ({e})")

    st.markdown('<p class="section-title">Negative mention rate by aspect — top 15 airlines</p>', unsafe_allow_html=True)
    try:
        df_flat_all = load_aspect_flat()
        df_neg  = df_flat_all[df_flat_all["ASPECT_SENTIMENT"] == "negative"].copy()
        df_tot2 = df_flat_all.groupby(["AIRLINE_NAME", "ASPECT_CATEGORY"])["CNT"].sum().reset_index()
        df_tot2.columns = ["AIRLINE_NAME", "ASPECT_CATEGORY", "TOTAL"]
        df_neg_m = df_neg.merge(df_tot2, on=["AIRLINE_NAME", "ASPECT_CATEGORY"])
        df_neg_m["NEG_PCT"] = (df_neg_m["CNT"] / df_neg_m["TOTAL"] * 100).round(1)
        top15_al = df_filtered.nlargest(15, "TOTAL_REVIEWS")["AIRLINE_NAME"].tolist()
        pivot_neg = df_neg_m[df_neg_m["AIRLINE_NAME"].isin(top15_al)].pivot_table(
            index="AIRLINE_NAME", columns="ASPECT_CATEGORY", values="NEG_PCT", aggfunc="mean",
        )
        fig_neg_hmap = px.imshow(
            pivot_neg, color_continuous_scale="Reds",
            range_color=[0, 100], text_auto=".0f", aspect="auto",
            labels={"color": "% negative"},
        )
        fig_neg_hmap.update_layout(
            height=380, margin=dict(l=0, r=0, t=10, b=10),
            coloraxis_colorbar=dict(len=0.7, thickness=12, title="% neg"),
        )
        st.plotly_chart(fig_neg_hmap, use_container_width=True)
    except Exception as e:
        st.info(f"Aspect flat view not yet available ({e})")


# ════════════════════════════════════════════════════════════════
# TAB 5 — REVIEWS EXPLORER
# ════════════════════════════════════════════════════════════════
with tab_reviews:
    st.markdown('<p class="section-title">Review explorer</p>', unsafe_allow_html=True)

    rcol1, rcol2, rcol3 = st.columns([1.5, 1, 1])
    with rcol1:
        review_airline = st.selectbox("Airline", airline_list, key="rev_airline")
    with rcol2:
        sentiment_filter = st.selectbox("Sentiment", ["All", "Positive", "Negative"], key="rev_sent")
    with rcol3:
        review_limit = st.slider("Reviews to show", 5, 50, 15, key="rev_limit")

    try:
        df_reviews = load_sample_reviews(review_airline, sentiment_filter, review_limit)
        if len(df_reviews):
            pos_ct = int((df_reviews["SENTIMENT_LABEL"] == "positive").sum())
            neg_ct = int((df_reviews["SENTIMENT_LABEL"] == "negative").sum())
            neu_ct = int((df_reviews["SENTIMENT_LABEL"] == "neutral").sum())
            st.markdown(
                f'<span class="badge-pos">▲ {pos_ct} positive</span> &nbsp;'
                f'<span class="badge-neg">▼ {neg_ct} negative</span> &nbsp;'
                f'<span class="badge-neu">— {neu_ct} neutral</span>',
                unsafe_allow_html=True,
            )
            st.markdown("<br>", unsafe_allow_html=True)
            for _, row in df_reviews.iterrows():
                sent  = str(row.get("SENTIMENT_LABEL", "neutral") or "neutral")
                badge = (
                    '<span class="badge-pos">positive</span>' if sent == "positive"
                    else '<span class="badge-neg">negative</span>' if sent == "negative"
                    else '<span class="badge-neu">neutral</span>'
                )
                border_color = "#1D9E75" if sent == "positive" else "#E24B4A" if sent == "negative" else "#3B8BD4"
                rating    = row.get("OVERALL_RATING", "?")
                score     = float(row.get("SENTIMENT_SCORE", 0) or 0)
                rating_llm   = str(row.get("RATING_LLM", "?") or "?")
                recommend_llm = str(row.get("RECOMMEND_LLM", "?") or "?")
                snippet   = str(row.get("REVIEW_SNIPPET", "") or "")
                seat      = str(row.get("SEAT_TYPE", "") or "")
                traveller = str(row.get("TRAVELLER_TYPE", "") or "")
                st.markdown(f"""
                <div style="background:#fff;border:1px solid #eee;border-radius:8px;
                            padding:0.9rem 1rem;margin-bottom:0.6rem;
                            border-left:3px solid {border_color}">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                        <div>{badge}&nbsp;<span style="font-size:0.8rem;color:#888">{seat} · {traveller}</span></div>
                        <div style="font-size:0.85rem;color:#555">
                            Rating: <b>{rating}</b>/10 &nbsp;|&nbsp;
                            Sentiment: <b>{score:+.3f}</b> &nbsp;|&nbsp;
                            LLM: <b>{rating_llm}</b> &nbsp;|&nbsp;
                            Recommend: <b>{recommend_llm}</b>
                        </div>
                    </div>
                    <div style="font-size:0.88rem;color:#333;line-height:1.5">{snippet}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No reviews found for the selected filters.")
    except Exception as e:
        st.error(f"Could not load reviews: {e}")


# ════════════════════════════════════════════════════════════════
# TAB 6 — AI REPORT
# ════════════════════════════════════════════════════════════════
with tab_report:
    st.markdown('<p class="section-title">Generate AI improvement brief</p>', unsafe_allow_html=True)
    st.markdown(
        "Uses **Snowflake Cortex Complete** (`mistral-large2`) to write a structured "
        "improvement report from the airline's worst-reviewed feedback."
    )

    rep_col1, rep_col2 = st.columns([1.5, 1])

    with rep_col1:
        report_airline = st.selectbox("Select airline", airline_list, key="rep_airline")
        report_style   = st.radio(
            "Report style",
            ["Executive brief (3 bullets)", "Detailed report (5 bullets)", "Email to operations manager"],
            horizontal=True,
        )
        num_reviews_used = st.slider("Worst reviews to analyse", 20, 200, 100, step=10)
        generate_btn = st.button("Generate AI report", use_container_width=True, type="primary")

    with rep_col2:
        if report_airline in df_kpis["AIRLINE_NAME"].values:
            r_kpi = df_kpis[df_kpis["AIRLINE_NAME"] == report_airline].iloc[0]
            st.markdown("**Airline snapshot**")
            st.metric("Reviews",      f"{int(r_kpi['TOTAL_REVIEWS']):,}")
            st.metric("Avg rating",   f"{float(r_kpi['AVG_RATING']):.1f} / 10")
            st.metric("Avg sentiment",f"{float(r_kpi['AVG_SENTIMENT']):+.3f}")
            st.metric("Recommend",    f"{float(r_kpi.get('RECOMMENDED_PCT', 0)):.0f}%")

    if generate_btn:
        with st.spinner(f"Fetching {num_reviews_used} worst reviews for {report_airline}…"):
            agg_text = load_worst_reviews_for_report(report_airline, num_reviews_used)

        if not agg_text:
            st.warning("No reviews found for this airline.")
        else:
            if report_style == "Executive brief (3 bullets)":
                instruction = (
                    f"Write a concise executive brief for {report_airline}. "
                    "List exactly 3 bullet points. Each bullet must have a bold heading (3–5 words), "
                    "one sentence describing the issue, and one sentence recommending a fix. "
                    "Keep the entire response under 200 words."
                )
            elif report_style == "Detailed report (5 bullets)":
                instruction = (
                    f"Write a detailed passenger experience report for {report_airline}. "
                    "Identify 5 key issues. For each: bold heading, one paragraph describing the issue "
                    "with evidence from reviews, and a specific recommendation with measurable targets. "
                    "Keep under 400 words."
                )
            else:
                instruction = (
                    f"Write a professional email from the Customer Intelligence Team to the "
                    f"Operations Manager at {report_airline}. Subject: Passenger Experience "
                    "Improvement Action Required. Body: 3 issue paragraphs each with a bold heading, "
                    "supporting evidence, and a recommendation. "
                    "Close with a request for a 2-week action plan. Under 350 words."
                )

            full_prompt = (
                f"[INST]### {instruction} "
                f"Reviews: {agg_text[:6000]} ###[/INST]"
            )

            with st.spinner("Cortex Complete generating report…"):
                try:
                    report_text = cortex_complete("mistral-large2", full_prompt, session)
                    st.markdown("---")
                    st.markdown(f"**AI-generated report — {report_airline}**")
                    st.markdown(
                        f'<div class="report-box">{report_text.replace(chr(10), "<br>")}</div>',
                        unsafe_allow_html=True,
                    )
                    st.download_button(
                        label="⬇ Download report as .txt",
                        data=report_text,
                        file_name=f"{report_airline.replace(' ', '_')}_improvement_brief.txt",
                        mime="text/plain",
                    )
                except Exception as e:
                    st.error(
                        f"Cortex Complete error: {e}\n\n"
                        "Check that your Snowflake region supports LLM functions: "
                        "https://docs.snowflake.com/user-guide/snowflake-cortex/llm-functions#availability"
                    )

    # Pre-computed summaries
    st.markdown("---")
    st.markdown('<p class="section-title">Pre-computed summaries (from notebook Phase 5b)</p>', unsafe_allow_html=True)
    try:
        df_pre = load_issues()
        if len(df_pre):
            show_airline = st.selectbox(
                "View summary for", df_pre["AIRLINE_NAME"].tolist(), key="pre_report"
            )
            row_pre = df_pre[df_pre["AIRLINE_NAME"] == show_airline]
            if len(row_pre):
                st.markdown(
                    f'<div class="report-box">'
                    f'{row_pre.iloc[0]["ISSUE_SUMMARY"].replace(chr(10), "<br>")}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No pre-computed summaries found. Run Phase 5b in the notebook first.")
    except Exception as e:
        st.info(f"Pre-computed summaries not yet available ({e})")
