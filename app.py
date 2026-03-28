from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="GCW Point Breakdown Explorer", layout="wide")

DATA_PATH = Path(__file__).parent / "data" / "gcw_points.csv"


@st.cache_data(show_spinner=False)
def load_data(csv_bytes: bytes | None = None) -> pd.DataFrame:
    if csv_bytes is None:
        df = pd.read_csv(DATA_PATH)
    else:
        df = pd.read_csv(pd.io.common.BytesIO(csv_bytes))

    df["logTimestamp"] = pd.to_datetime(
        df["logTimestamp"], format="%b %d, %Y @ %H:%M:%S.%f", errors="coerce"
    )
    df["pointValue"] = pd.to_numeric(df["pointValue"], errors="coerce").fillna(0)
    df["planet"] = df["planet"].fillna("unknown").replace({"null": "unknown"})
    df["faction"] = df["faction"].fillna("unknown")
    df["reason"] = df["reason"].fillna("unknown")
    df["source"] = df["source"].fillna("unknown")
    return df


def metric_delta_text(series: pd.Series) -> str:
    if series.empty:
        return "No data"
    leader = series.idxmax()
    margin = series.max() - series.min() if len(series) > 1 else series.max()
    return f"{leader} by {margin:,.1f}"


def leaderboard_table(df: pd.DataFrame, group_col: str, top_n: int = 15) -> pd.DataFrame:
    table = (
        df.groupby(group_col, dropna=False)
        .agg(
            events=("pointValue", "size"),
            total_points=("pointValue", "sum"),
            avg_points=("pointValue", "mean"),
        )
        .sort_values("total_points", ascending=False)
        .head(top_n)
        .reset_index()
    )
    table["total_points"] = table["total_points"].round(2)
    table["avg_points"] = table["avg_points"].round(2)
    return table


def grouped_totals(df: pd.DataFrame, primary: str, split_by: str) -> pd.DataFrame:
    if split_by == "None":
        result = (
            df.groupby(primary, dropna=False, as_index=False)["pointValue"]
            .sum()
            .sort_values("pointValue", ascending=False)
        )
        result["split"] = "All"
        return result.rename(columns={primary: "group"})

    result = (
        df.groupby([primary, split_by], dropna=False, as_index=False)["pointValue"]
        .sum()
        .sort_values("pointValue", ascending=False)
    )
    return result.rename(columns={primary: "group", split_by: "split"})


def chart_frame(df: pd.DataFrame, index_col: str, column_col: str, value_col: str) -> pd.DataFrame:
    frame = df.pivot_table(
        index=index_col,
        columns=column_col,
        values=value_col,
        aggfunc="sum",
        fill_value=0,
    )
    return frame.sort_index()


st.title("GCW Point Breakdown Explorer")
st.caption("Interactive stats for your GCW point breakdown sheet, centered on totals and rankings by reason.")

uploaded_file = st.sidebar.file_uploader("Replace the bundled CSV", type=["csv"])
df = load_data(uploaded_file.getvalue() if uploaded_file else None)

min_time = df["logTimestamp"].min()
max_time = df["logTimestamp"].max()

st.sidebar.header("Filters")
factions = st.sidebar.multiselect(
    "Faction", options=sorted(df["faction"].dropna().unique()), default=sorted(df["faction"].dropna().unique())
)
planets = st.sidebar.multiselect(
    "Planet", options=sorted(df["planet"].dropna().unique()), default=sorted(df["planet"].dropna().unique())
)
reasons = st.sidebar.multiselect(
    "Reason", options=sorted(df["reason"].dropna().unique()), default=sorted(df["reason"].dropna().unique())
)
date_range = st.sidebar.date_input(
    "Date range",
    value=(min_time.date(), max_time.date()),
    min_value=min_time.date(),
    max_value=max_time.date(),
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = end_date = min_time.date()

filtered = df[
    df["faction"].isin(factions)
    & df["planet"].isin(planets)
    & df["reason"].isin(reasons)
    & df["logTimestamp"].dt.date.between(start_date, end_date)
].copy()

if filtered.empty:
    st.warning("No rows match the current filters.")
    st.stop()

faction_totals = filtered.groupby("faction")["pointValue"].sum().sort_values(ascending=False)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Events", f"{len(filtered):,}")
col2.metric("Total points", f"{filtered['pointValue'].sum():,.1f}")
col3.metric("Avg event value", f"{filtered['pointValue'].mean():,.2f}")
col4.metric("Faction lead", metric_delta_text(faction_totals))

timeline = (
    filtered.assign(day=filtered["logTimestamp"].dt.floor("D"))
    .groupby(["day", "faction"], as_index=False)["pointValue"]
    .sum()
)

primary_dimension = st.selectbox(
    "Show totals by",
    options=["reason", "planet", "faction"],
    index=0,
)
split_dimension = st.selectbox(
    "Split totals by",
    options=["faction", "planet", "reason", "None"],
    index=0,
)

if primary_dimension == split_dimension:
    split_dimension = "None"

breakdown = grouped_totals(filtered, primary_dimension, split_dimension)
top_reasons = leaderboard_table(filtered, "reason")
top_planets = leaderboard_table(filtered, "planet")

left, right = st.columns(2)

with left:
    st.subheader("Points over time")
    timeline_chart = chart_frame(timeline, "day", "faction", "pointValue")
    st.line_chart(timeline_chart, height=350, use_container_width=True)

with right:
    st.subheader(f"Totals by {primary_dimension}")
    breakdown_chart = chart_frame(breakdown, "group", "split", "pointValue")
    breakdown_chart["Total"] = breakdown_chart.sum(axis=1)
    breakdown_chart = breakdown_chart.sort_values("Total", ascending=False).drop(columns="Total").head(20)
    st.bar_chart(breakdown_chart, height=350, use_container_width=True)

table_left, table_right = st.columns(2)

with table_left:
    st.subheader("Top reasons by total points")
    st.dataframe(top_reasons, use_container_width=True, hide_index=True)

with table_right:
    st.subheader("Top planets by total points")
    st.dataframe(top_planets, use_container_width=True, hide_index=True)

st.subheader("Reason breakdown pivot")
reason_pivot = pd.pivot_table(
    filtered,
    index="reason",
    columns="faction",
    values="pointValue",
    aggfunc="sum",
    fill_value=0,
)
reason_pivot["Total"] = reason_pivot.sum(axis=1)
reason_pivot = reason_pivot.sort_values("Total", ascending=False)
st.dataframe(reason_pivot.round(2), use_container_width=True)

st.subheader("Highest-value source events")
top_source_events = (
    filtered.sort_values(["pointValue", "logTimestamp"], ascending=[False, False])[
        ["logTimestamp", "faction", "planet", "reason", "pointValue", "source"]
    ]
    .head(25)
    .reset_index(drop=True)
)
st.dataframe(top_source_events, use_container_width=True, hide_index=True)

st.subheader("Raw data")
display_df = filtered.sort_values("logTimestamp", ascending=False).copy()
display_df = display_df[["logTimestamp", "faction", "planet", "reason", "pointValue", "source"]]
st.dataframe(display_df, use_container_width=True, hide_index=True)
