"""OEM Contract Awards Tracker — Streamlit dashboard.

Reads the processed dataset produced by refresh.py and renders one clean
dashboard per OEM family, plus Registry Review and Data Quality pages.

Run:  streamlit run app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd
import streamlit as st

import config
import dashboard_tables as dt
import charts
import exporter
from company_registry import load_registry

st.set_page_config(page_title="OEM Award Tracker", layout="wide")

# Minimal styling: tighten spacing, calm the default chrome. Data over flash.
st.markdown(
    """
    <style>
      .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px;}
      [data-testid="stMetricValue"] {font-size: 1.35rem;}
      h1, h2, h3 {font-weight: 600;}
      hr {margin: 0.8rem 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

PAGES = list(config.PARENT_COMPANIES) + ["Registry Review", "Data Quality"]


def _safe_read_csv(path):
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def _load():
    df = dt.load_processed()
    summary = json.loads(config.SUMMARY_JSON.read_text()) if config.SUMMARY_JSON.exists() else {}
    unmapped = _safe_read_csv(config.UNMAPPED_CSV)
    rejected = _safe_read_csv(config.REJECTED_CSV)
    return df, summary, unmapped, rejected


def fmt_money(v):
    try:
        return f"${float(v):,.0f}"
    except (ValueError, TypeError):
        return "-"


def money_cols(df, cols):
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(lambda x: fmt_money(x) if pd.notna(x) else "")
    return df


LINK_CFG = {"USAspending Link": st.column_config.LinkColumn("USAspending", display_text="view")}

# --------------------------------------------------------------------------- #
df, summary, unmapped_df, rejected_df = _load()

st.sidebar.title("OEM Award Tracker")
page = st.sidebar.radio("Company", PAGES, label_visibility="collapsed")
st.sidebar.markdown("---")
last_ref = summary.get("last_refreshed", "never")
st.sidebar.caption(f"Last refreshed: {last_ref}")
st.sidebar.caption(f"Data source: {config.DATA_SOURCE_LABEL}")
st.sidebar.caption("Refreshed daily. Figures may include reporting delays.")
if df.empty:
    st.sidebar.warning("No processed data yet. Run `python refresh.py`.")


def render_company(company: str):
    cdf = dt.filter_company(df, company)
    st.title(company)
    st.caption(f"Last refreshed: {last_ref}  ·  Data source: {config.DATA_SOURCE_LABEL}")

    if cdf.empty:
        st.info("No contracts awarded since 2023 found for this company in the latest refresh.")
        return

    k = dt.kpis(cdf)
    c = st.columns(4)
    c[0].metric("Contracts (2023+)", f"{k['Contracts (2023+)']:,}")
    c[1].metric("Active Contracts", f"{k['Active Contracts']:,}")
    c[2].metric("Total Potential Value", fmt_money(k["Total Potential Value"]))
    c[3].metric("Total Obligated", fmt_money(k["Total Obligated Amount"]))
    c = st.columns(4)
    c[0].metric("Recipient Entities", k["Recipient Entities"])
    c[1].metric("Largest Active Award", fmt_money(k["Largest Active Award"]))
    c[2].metric("Top Department", k["Top Awarding Department"])
    c[3].metric("Most Recent Award", k["Most Recent Award Date"])

    st.markdown("---")

    # 10 most recent contracts awarded
    st.subheader("10 Most Recent Contracts Awarded")
    st.caption("Newest by award date, per USAspending. Includes active and completed performance periods.")
    latest = dt.latest_awards(cdf, 10)
    st.dataframe(money_cols(latest, ["Potential Value", "Obligated Amount"]),
                 use_container_width=True, hide_index=True, column_config=LINK_CFG)
    st.download_button("Download these 10 (CSV)", exporter.df_to_csv_bytes(latest),
                       f"{company}_recent10.csv", "text/csv", key="recent")

    # 10 largest active
    st.subheader("10 Largest Active Awards by Potential Value")
    st.caption(f"Performance period ends on/after today ({summary.get('current_date', config.current_date())}). "
               "Ranked by potential value (base + all options); falls back to obligated amount where missing — see Value Basis.")
    largest = dt.largest_awards(cdf, 10)
    if largest.empty:
        st.info("No currently-active awards for this company in the latest refresh.")
    else:
        st.dataframe(money_cols(largest, ["Potential Value", "Obligated Amount"]),
                     use_container_width=True, hide_index=True, column_config=LINK_CFG)
        st.download_button("Download these 10 (CSV)", exporter.df_to_csv_bytes(largest),
                           f"{company}_largest10.csv", "text/csv", key="largest")

    # categories
    st.subheader("Award Categories")
    cat = dt.category_tallies(cdf)
    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(money_cols(cat, ["Total Potential Value", "Total Obligated Amount"]),
                     use_container_width=True, hide_index=True)
    with col2:
        st.plotly_chart(charts.bar(cat, "Award Category", "Contract Count",
                                   "By contract count"), use_container_width=True)

    # locations
    st.subheader("Performance Locations")
    loc = dt.location_counts(cdf)
    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(money_cols(loc.head(25), ["Total Potential Value", "Total Obligated Amount"]),
                     use_container_width=True, hide_index=True)
    with col2:
        st.plotly_chart(charts.bar(loc, "Performance Location", "Contract Count",
                                   "Top locations by contract count"), use_container_width=True)

    # subsidiaries
    st.subheader("Subsidiary / Recipient Breakdown")
    sub = dt.subsidiary_breakdown(cdf)
    st.dataframe(money_cols(sub, ["Total Potential Value", "Total Obligated Amount"]),
                 use_container_width=True, hide_index=True)

    # full table
    st.subheader("Full Award Table")
    render_full_table(cdf, company)


def render_full_table(cdf: pd.DataFrame, company: str):
    with st.expander("Filters & search", expanded=False):
        search = st.text_input("Search description, recipient, office, PIID, or location", key=f"s_{company}")
        fc1, fc2, fc3 = st.columns(3)
        dept = fc1.multiselect("Awarding Department", sorted(cdf["Awarding Department"].dropna().unique()), key=f"d_{company}")
        cat = fc2.multiselect("Award Category", sorted(cdf["Award Category"].dropna().unique()), key=f"c_{company}")
        rec = fc3.multiselect("Recipient / Subsidiary", sorted(cdf["Recipient Legal Name"].dropna().unique()), key=f"r_{company}")
        fc4, fc5, fc6 = st.columns(3)
        atype = fc4.multiselect("Award Type", sorted(cdf["Award Type"].dropna().unique()), key=f"t_{company}")
        action = fc5.multiselect("Action Classification", sorted(cdf["Action Classification"].dropna().unique()), key=f"a_{company}")
        state = fc6.multiselect("State", sorted(cdf["Performance State"].dropna().unique()), key=f"st_{company}")
        g1, g2 = st.columns(2)
        active_choice = g1.radio("Performance status", ["All", "Active only", "Completed only"],
                                 horizontal=True, key=f"act_{company}")
        new_only = g2.checkbox("New awards only (exclude modifications)", key=f"new_{company}")

    f = cdf.copy()
    if search:
        s = search.lower()
        cols = ["Award Description", "Recipient Legal Name", "Awarding Subagency",
                "Award ID / PIID", "Full Performance Location"]
        mask = pd.Series(False, index=f.index)
        for col in cols:
            if col in f.columns:
                mask |= f[col].astype(str).str.lower().str.contains(s, na=False)
        f = f[mask]
    if dept:
        f = f[f["Awarding Department"].isin(dept)]
    if cat:
        f = f[f["Award Category"].isin(cat)]
    if rec:
        f = f[f["Recipient Legal Name"].isin(rec)]
    if atype:
        f = f[f["Award Type"].isin(atype)]
    if action:
        f = f[f["Action Classification"].isin(action)]
    if state:
        f = f[f["Performance State"].isin(state)]
    if active_choice == "Active only":
        f = f[f["Currently Active"] == "Yes"]
    elif active_choice == "Completed only":
        f = f[f["Currently Active"] == "No"]
    if new_only:
        f = f[f["Action Classification"].astype(str).str.startswith("New")]

    st.caption(f"{len(f):,} of {len(cdf):,} contracts")
    st.dataframe(money_cols(f, ["Potential Value", "Obligated Amount"]),
                 use_container_width=True, hide_index=True, column_config=LINK_CFG)
    d1, d2 = st.columns(2)
    d1.download_button("Download table (CSV)", exporter.df_to_csv_bytes(f),
                       f"{company}_awards.csv", "text/csv", key=f"csv_{company}")
    d2.download_button("Download table (Excel)", exporter.df_to_excel_bytes(f),
                       f"{company}_awards.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"xl_{company}")


def render_registry_review():
    st.title("Registry Review")
    st.caption("Curated parent-company mapping and unmapped fuzzy candidates awaiting review.")
    st.subheader("Curated OEM Registry")
    st.dataframe(pd.read_csv(config.REGISTRY_CSV), use_container_width=True, hide_index=True)

    st.subheader("Unmapped Candidates")
    if unmapped_df.empty:
        st.success("No unmapped candidates flagged in the last refresh.")
    else:
        st.dataframe(money_cols(unmapped_df, ["Total Potential Value"]),
                     use_container_width=True, hide_index=True)
        st.download_button("Download unmapped candidates (CSV)",
                           exporter.df_to_csv_bytes(unmapped_df),
                           "unmapped_candidates.csv", "text/csv")
        st.info("Fuzzy matches are not shown in dashboards. Add verified entities to "
                "data/registry/oem_registry.csv and re-run the refresh.")


def render_data_quality():
    st.title("Data Quality")
    if not summary:
        st.info("No refresh summary yet. Run `python refresh.py`.")
        return
    st.caption(f"Last refreshed: {summary.get('last_refreshed')}  ·  Current date: {summary.get('current_date')}")

    c = st.columns(4)
    c[0].metric("Raw records pulled", f"{summary.get('raw_records', 0):,}")
    c[1].metric("Accepted (2023+ contracts)", f"{summary.get('accepted_records', 0):,}")
    c[2].metric("Rejected", f"{summary.get('rejected_records', 0):,}")
    c[3].metric("Unmapped candidates", f"{summary.get('unmapped_candidates', 0):,}")
    c = st.columns(3)
    c[0].metric("Missing potential value", f"{summary.get('records_missing_potential_value', 0):,}")
    c[1].metric("Using obligated fallback", f"{summary.get('records_using_obligated_fallback', 0):,}")
    c[2].metric("Low category confidence", f"{summary.get('records_low_category_confidence', 0):,}")

    if summary.get("records_using_obligated_fallback", 0):
        st.warning("Some awards use obligated amount because potential value is missing (see Value Basis).")
    if summary.get("records_low_category_confidence", 0):
        st.warning("Some award categories are low-confidence and flagged for review.")
    if summary.get("records_low_date_confidence", 0):
        st.warning("Some awards have missing current end dates; active status inferred from potential end date.")

    st.subheader("Rejected records")
    if rejected_df.empty:
        st.success("No rejected records.")
    else:
        if "Rejection Reason" in rejected_df.columns:
            st.dataframe(rejected_df["Rejection Reason"].value_counts()
                         .rename_axis("Rejection Reason").reset_index(name="Count"),
                         use_container_width=True, hide_index=True)

    st.subheader("Refresh log")
    if config.REFRESH_LOG.exists():
        st.dataframe(_safe_read_csv(config.REFRESH_LOG), use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
if page == "Registry Review":
    render_registry_review()
elif page == "Data Quality":
    render_data_quality()
else:
    render_company(page)
