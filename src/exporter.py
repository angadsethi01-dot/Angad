"""CSV / Excel export helpers."""
from __future__ import annotations

import io
from typing import Dict, Optional

import pandas as pd

import config
import dashboard_tables as dt


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Awards") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name=sheet_name[:31], index=False)
    return buffer.getvalue()


def build_full_excel(df: pd.DataFrame,
                     unmapped: Optional[pd.DataFrame] = None,
                     rejected: Optional[pd.DataFrame] = None) -> bytes:
    """Multi-sheet workbook: all-companies + per-company + tallies + locations."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as xl:
        dt.company_rollup(df).to_excel(xl, sheet_name="All Companies Summary", index=False)
        for company in config.PARENT_COMPANIES:
            cdf = dt.filter_company(df, company)
            sheet = company.replace(" / ", "-")[:31]
            (cdf if not cdf.empty else pd.DataFrame(columns=df.columns)).to_excel(
                xl, sheet_name=sheet, index=False)
        dt.category_tallies(df).to_excel(xl, sheet_name="Category Tallies", index=False)
        dt.location_counts(df).to_excel(xl, sheet_name="Location Counts", index=False)
        if unmapped is not None and not unmapped.empty:
            unmapped.to_excel(xl, sheet_name="Unmapped Candidates", index=False)
        if rejected is not None and not rejected.empty:
            rejected.head(50000).to_excel(xl, sheet_name="Rejected Records", index=False)
    return buffer.getvalue()
