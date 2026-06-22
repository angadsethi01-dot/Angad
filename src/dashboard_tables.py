"""Aggregations powering each dashboard section (KPIs, latest/largest, tallies)."""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

import config

LATEST_COLUMNS = [
    "Award Date", "Award Description", "Awarding Department", "Awarding Subagency",
    "Full Performance Location", "Period of Performance Start Date",
    "Period of Performance Current End Date",
    "Potential Value", "Obligated Amount", "Recipient Legal Name",
    "Award Category", "Award Type", "Action Classification", "Currently Active",
    "USAspending Link",
]

LARGEST_COLUMNS = [
    "Award Description", "Awarding Department", "Awarding Subagency",
    "Full Performance Location", "Period of Performance Start Date",
    "Period of Performance Current End Date", "Period of Performance Potential End Date",
    "Potential Value", "Obligated Amount", "Value Basis", "Recipient Legal Name",
    "Award Category", "Award Type", "Action Classification",
    "USAspending Link",
]


def load_processed() -> pd.DataFrame:
    df = pd.DataFrame(columns=[])
    if config.PROCESSED_CSV.exists():
        try:
            df = pd.read_csv(config.PROCESSED_CSV)
        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=[])
    for c in ("Award Date", "Period of Performance Start Date",
              "Period of Performance Current End Date",
              "Period of Performance Potential End Date"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def filter_company(df: pd.DataFrame, company: str) -> pd.DataFrame:
    if company == "All Companies" or "OEM Parent Company" not in df.columns:
        return df
    return df[df["OEM Parent Company"] == company]


def active_only(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Currently Active" not in df.columns:
        return df
    return df[df["Currently Active"] == "Yes"]


def kpis(df: pd.DataFrame) -> Dict:
    empty = {"Contracts (2023+)": 0, "Active Contracts": 0, "Total Potential Value": 0,
             "Total Obligated Amount": 0, "Recipient Entities": 0,
             "Top Awarding Department": "-", "Top Performance Location": "-",
             "Largest Active Award": 0, "Most Recent Award Date": "-"}
    if df.empty:
        return empty

    def top(col):
        if col not in df.columns or df[col].dropna().empty:
            return "-"
        vc = df[col].dropna()
        return vc.value_counts().idxmax() if not vc.empty else "-"

    act = active_only(df)
    return {
        "Contracts (2023+)": int(len(df)),
        "Active Contracts": int(len(act)),
        "Total Potential Value": float(df["Potential Value"].fillna(0).sum()),
        "Total Obligated Amount": float(df["Obligated Amount"].fillna(0).sum()),
        "Recipient Entities": int(df["Recipient Legal Name"].nunique()),
        "Top Awarding Department": top("Awarding Department"),
        "Top Performance Location": top("Full Performance Location"),
        "Largest Active Award": float(act["Potential Value"].fillna(act["Obligated Amount"]).max() or 0) if not act.empty else 0,
        "Most Recent Award Date": (df["Award Date"].max().date().isoformat()
                                   if df["Award Date"].notna().any() else "-"),
    }


def latest_awards(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """10 most recent contracts awarded (by award date), regardless of active status."""
    if df.empty:
        return df
    out = df.sort_values("Award Date", ascending=False, na_position="last").head(n)
    cols = [c for c in LATEST_COLUMNS if c in out.columns]
    return out[cols].reset_index(drop=True)


def largest_awards(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """10 largest CURRENTLY ACTIVE awards by potential value (perf end >= today)."""
    act = active_only(df)
    if act.empty:
        return act
    tmp = act.copy()
    # rank by potential value, fall back to obligated amount
    tmp["_rank"] = tmp["Potential Value"].fillna(tmp["Obligated Amount"])
    out = tmp.sort_values("_rank", ascending=False, na_position="last").head(n)
    cols = [c for c in LARGEST_COLUMNS if c in out.columns]
    return out[cols].reset_index(drop=True)


def category_tallies(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Award Category" not in df.columns:
        return pd.DataFrame(columns=["Award Category", "Contract Count",
                                     "Total Potential Value", "Total Obligated Amount",
                                     "Share of Company Awards"])
    g = df.groupby("Award Category").agg(
        **{"Contract Count": ("Award Category", "size"),
           "Total Potential Value": ("Potential Value", lambda s: s.fillna(0).sum()),
           "Total Obligated Amount": ("Obligated Amount", lambda s: s.fillna(0).sum())}
    ).reset_index()
    total = g["Contract Count"].sum()
    g["Share of Company Awards"] = (g["Contract Count"] / total * 100).round(1).astype(str) + "%"
    return g.sort_values("Contract Count", ascending=False).reset_index(drop=True)


def location_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Full Performance Location" not in df.columns:
        return pd.DataFrame(columns=["Performance Location", "Contract Count",
                                     "Total Potential Value", "Total Obligated Amount"])
    g = df.groupby("Full Performance Location").agg(
        **{"Contract Count": ("Full Performance Location", "size"),
           "Total Potential Value": ("Potential Value", lambda s: s.fillna(0).sum()),
           "Total Obligated Amount": ("Obligated Amount", lambda s: s.fillna(0).sum())}
    ).reset_index().rename(columns={"Full Performance Location": "Performance Location"})
    return g.sort_values("Contract Count", ascending=False).reset_index(drop=True)


def subsidiary_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Recipient Legal Name" not in df.columns:
        return pd.DataFrame(columns=["Recipient Legal Name", "Parent Company",
                                     "Contract Count", "Total Potential Value",
                                     "Total Obligated Amount", "Top Awarding Department",
                                     "Top Award Category", "Mapping Confidence"])
    def mode_or_dash(s):
        s = s.dropna()
        return s.value_counts().idxmax() if not s.empty else "-"
    g = df.groupby("Recipient Legal Name").agg(
        **{"Parent Company": ("OEM Parent Company", mode_or_dash),
           "Contract Count": ("Recipient Legal Name", "size"),
           "Total Potential Value": ("Potential Value", lambda s: s.fillna(0).sum()),
           "Total Obligated Amount": ("Obligated Amount", lambda s: s.fillna(0).sum()),
           "Top Awarding Department": ("Awarding Department", mode_or_dash),
           "Top Award Category": ("Award Category", mode_or_dash),
           "Mapping Confidence": ("Mapping Confidence", mode_or_dash)}
    ).reset_index()
    return g.sort_values("Total Potential Value", ascending=False).reset_index(drop=True)


def company_rollup(df: pd.DataFrame) -> pd.DataFrame:
    """All-Companies overview table."""
    if df.empty:
        return pd.DataFrame(columns=["OEM Parent Company", "Current Awards",
                                     "Total Potential Value", "Total Obligated Amount",
                                     "Largest Award", "Most Recent Award"])
    rows = []
    for company, g in df.groupby("OEM Parent Company"):
        rows.append({
            "OEM Parent Company": company,
            "Current Awards": int(len(g)),
            "Total Potential Value": float(g["Potential Value"].fillna(0).sum()),
            "Total Obligated Amount": float(g["Obligated Amount"].fillna(0).sum()),
            "Largest Award": float(g["Potential Value"].fillna(g["Obligated Amount"]).max() or 0),
            "Most Recent Award": (g["Award Date"].max().date().isoformat()
                                  if g["Award Date"].notna().any() else "-"),
        })
    return pd.DataFrame(rows).sort_values("Total Potential Value", ascending=False).reset_index(drop=True)
