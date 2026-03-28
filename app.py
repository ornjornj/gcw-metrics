from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(page_title="GCW Point Breakdown Explorer", layout="wide")

DATA_PATH = Path(__file__).parent / "data" / "gcw_points.csv"
FACTION_COLORS = {
    "Rebel": "#e53935",
    "Imperial": "#1e88e5",
}
TYPE_PALETTE = px.colors.qualitative.Set3 + px.colors.qualitative.Safe + px.colors.qualitative.Bold

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        min-width: 24rem;
    }
    [data-testid="stMultiSelect"] [data-baseweb="tag"] {
        max-width: 100%;
        height: auto;
    }
    [data-testid="stMultiSelect"] [data-baseweb="tag"] span {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
        line-height: 1.2;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2.6rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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
    df["type"] = df["reason"]
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
            activities=("pointValue", "size"),
            total_points=("pointValue", "sum"),
        )
        .sort_values("total_points", ascending=False)
        .head(top_n)
        .reset_index()
    )
    table["total_points"] = table["total_points"].round(2)
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


def grouped_timeseries(df: pd.DataFrame, time_grain: str, group_col: str, value_mode: str) -> pd.DataFrame:
    freq = "D" if time_grain == "Daily" else "H"
    prepared = df.assign(period=df["logTimestamp"].dt.floor(freq))
    if value_mode == "Points":
        grouped = (
            prepared.groupby(["period", group_col], as_index=False)["pointValue"]
            .sum()
            .rename(columns={"pointValue": "value"})
        )
    else:
        grouped = (
            prepared.groupby(["period", group_col], as_index=False)
            .size()
            .rename(columns={"size": "value"})
        )
    return chart_frame(grouped, "period", group_col, "value")


def grouped_timeseries_long(df: pd.DataFrame, time_grain: str, group_col: str, value_mode: str) -> pd.DataFrame:
    freq = "D" if time_grain == "Daily" else "H"
    prepared = df.assign(period=df["logTimestamp"].dt.floor(freq))
    if value_mode == "Points":
        return (
            prepared.groupby(["period", group_col], as_index=False)["pointValue"]
            .sum()
            .rename(columns={"pointValue": "value", group_col: "group"})
        )
    return (
        prepared.groupby(["period", group_col], as_index=False)
        .size()
        .rename(columns={"size": "value", group_col: "group"})
    )


def short_label(text: str, limit: int = 24) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def unique_short_labels(values: list[str], limit: int = 24) -> dict[str, str]:
    result: dict[str, str] = {}
    used: set[str] = set()
    for value in values:
        candidate = short_label(value, limit)
        if candidate not in used:
            result[value] = candidate
            used.add(candidate)
            continue
        i = 2
        while True:
            suffix = f" ({i})"
            trimmed = short_label(value, max(8, limit - len(suffix))) + suffix
            if trimmed not in used:
                result[value] = trimmed
                used.add(trimmed)
                break
            i += 1
    return result


def ordered_faction_columns(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = [name for name in ["Rebel", "Imperial"] if name in frame.columns]
    ordered.extend([name for name in frame.columns if name not in ordered])
    return frame[ordered]


def faction_line_figure(frame: pd.DataFrame, title_y: str) -> go.Figure:
    frame = ordered_faction_columns(frame)
    fig = go.Figure()
    for column in frame.columns:
        fig.add_trace(
            go.Scatter(
                x=frame.index,
                y=frame[column],
                mode="lines",
                name=column,
                line={"color": FACTION_COLORS.get(column, "#9aa5b1"), "width": 3},
            )
        )
    fig.update_layout(
        height=320,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        yaxis_title=title_y,
        legend_title_text="Faction",
    )
    return fig


def type_line_figure(df: pd.DataFrame, title_y: str) -> go.Figure:
    names = df["group"].drop_duplicates().tolist()
    label_map = unique_short_labels(names, limit=22)
    plot_df = df.copy()
    plot_df["display_group"] = plot_df["group"].map(label_map)
    color_map = {
        label_map[name]: TYPE_PALETTE[idx % len(TYPE_PALETTE)]
        for idx, name in enumerate(names)
    }
    fig = px.line(
        plot_df,
        x="period",
        y="value",
        color="display_group",
        color_discrete_map=color_map,
        custom_data=["group"],
        labels={"period": "", "value": title_y, "display_group": "Type"},
    )
    fig.update_traces(
        mode="lines",
        line={"width": 2.5},
        hovertemplate="Type: %{customdata[0]}<br>Time: %{x}<br>"
        + f"{title_y}: "
        + "%{y:,.0f}<extra></extra>",
    )
    fig.update_layout(
        height=320,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        yaxis_title=title_y,
        legend_title_text="Type",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": -0.35,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
        },
    )
    return fig


def breakdown_bar_figure(df: pd.DataFrame, primary_dimension: str) -> go.Figure:
    fig = px.bar(
        df,
        x="pointValue",
        y="group",
        color="split",
        orientation="h",
        labels={"pointValue": "Points", "group": primary_dimension.title(), "split": "Split"},
    )
    if set(df["split"].unique()).issubset(set(FACTION_COLORS) | {"All"}):
        color_map = {**FACTION_COLORS, "All": "#90a4ae"}
        for trace in fig.data:
            trace.marker.color = color_map.get(trace.name, "#90a4ae")
    fig.update_layout(height=350, margin={"l": 10, "r": 10, "t": 10, "b": 10}, yaxis={"categoryorder": "total ascending"})
    return fig


st.title("GCW Point Breakdown Explorer")
st.caption("Interactive stats for your GCW point breakdown sheet, centered on totals and rankings by type.")

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
    "Type", options=sorted(df["type"].dropna().unique()), default=sorted(df["type"].dropna().unique())
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
    & df["type"].isin(reasons)
    & df["logTimestamp"].dt.date.between(start_date, end_date)
].copy()

if filtered.empty:
    st.warning("No rows match the current filters.")
    st.stop()

faction_totals = filtered.groupby("faction")["pointValue"].sum().sort_values(ascending=False)
type_totals = filtered.groupby("type")["pointValue"].sum().sort_values(ascending=False)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Activities", f"{len(filtered):,}")
col2.metric("Total points", f"{filtered['pointValue'].sum():,.1f}")
col3.metric("Top type", type_totals.index[0] if not type_totals.empty else "No data")
col4.metric("Faction lead", metric_delta_text(faction_totals))

primary_dimension = st.selectbox(
    "Show totals by",
    options=["type", "planet", "faction"],
    index=0,
)
split_dimension = st.selectbox(
    "Split totals by",
    options=["faction", "planet", "type", "None"],
    index=0,
)
time_grain = st.radio("Time grain", options=["Daily", "Hourly"], horizontal=True)
top_type_count = st.slider("Top types to chart over time", min_value=3, max_value=12, value=8)

if primary_dimension == split_dimension:
    split_dimension = "None"

breakdown = grouped_totals(filtered, primary_dimension, split_dimension)
top_types = leaderboard_table(filtered, "type")
top_types_by_activity = (
    filtered.groupby("type", dropna=False)
    .agg(activities=("pointValue", "size"), total_points=("pointValue", "sum"))
    .sort_values(["activities", "total_points"], ascending=False)
    .head(15)
    .reset_index()
)
top_planets_by_activity = (
    filtered.groupby("planet", dropna=False)
    .agg(activities=("pointValue", "size"), total_points=("pointValue", "sum"))
    .sort_values(["activities", "total_points"], ascending=False)
    .head(15)
    .reset_index()
)
top_sources = leaderboard_table(filtered, "source", top_n=25)

faction_points_chart = grouped_timeseries(filtered, time_grain, "faction", "Points")
faction_activity_chart = grouped_timeseries(filtered, time_grain, "faction", "Activities")
top_type_names = top_types["type"].head(top_type_count).tolist()
type_slice = filtered[filtered["type"].isin(top_type_names)].copy()
type_points_chart = grouped_timeseries_long(type_slice, time_grain, "type", "Points")
type_activity_chart = grouped_timeseries_long(type_slice, time_grain, "type", "Activities")

left, right = st.columns(2)

with left:
    st.subheader("Points over time by faction")
    st.plotly_chart(faction_line_figure(faction_points_chart, "Points"), use_container_width=True)

with right:
    st.subheader(f"Totals by {primary_dimension}")
    breakdown_chart = chart_frame(breakdown, "group", "split", "pointValue")
    breakdown_chart["Total"] = breakdown_chart.sum(axis=1)
    breakdown_chart = breakdown_chart.sort_values("Total", ascending=False).drop(columns="Total").head(20)
    breakdown_plot_df = breakdown_chart.reset_index().melt(id_vars="group", var_name="split", value_name="pointValue")
    breakdown_plot_df = breakdown_plot_df[breakdown_plot_df["pointValue"] > 0]
    st.plotly_chart(breakdown_bar_figure(breakdown_plot_df, primary_dimension), use_container_width=True)

time_left, time_right = st.columns(2)

with time_left:
    st.subheader("Points over time by type")
    st.plotly_chart(type_line_figure(type_points_chart, "Points"), use_container_width=True)

with time_right:
    st.subheader("Activities over time by faction")
    st.plotly_chart(faction_line_figure(faction_activity_chart, "Activities"), use_container_width=True)

activity_left, activity_right = st.columns(2)

with activity_left:
    st.subheader("Activities over time by type")
    st.plotly_chart(type_line_figure(type_activity_chart, "Activities"), use_container_width=True)

with activity_right:
    st.subheader("Top types by activities")
    st.dataframe(top_types_by_activity, use_container_width=True, hide_index=True)

table_left, table_right = st.columns(2)

with table_left:
    st.subheader("Top types by total points")
    st.dataframe(top_types, use_container_width=True, hide_index=True)

with table_right:
    st.subheader("Most active planets")
    st.dataframe(top_planets_by_activity, use_container_width=True, hide_index=True)

st.subheader("Type breakdown pivot")
type_pivot = pd.pivot_table(
    filtered,
    index="type",
    columns="faction",
    values="pointValue",
    aggfunc="sum",
    fill_value=0,
)
type_pivot["Total"] = type_pivot.sum(axis=1)
type_pivot = type_pivot.sort_values("Total", ascending=False)
st.dataframe(type_pivot.round(2), use_container_width=True)

st.subheader("Highest-value source events")
top_source_events = (
    filtered.sort_values(["pointValue", "logTimestamp"], ascending=[False, False])[
        ["logTimestamp", "faction", "planet", "type", "pointValue", "source"]
    ]
    .head(25)
    .reset_index(drop=True)
)
st.dataframe(top_source_events, use_container_width=True, hide_index=True)

st.subheader("Raw data")
display_df = filtered.sort_values("logTimestamp", ascending=False).copy()
display_df = display_df[["logTimestamp", "faction", "planet", "type", "pointValue", "source"]]
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.subheader("Top sources by total points")
st.dataframe(top_sources, use_container_width=True, hide_index=True)
