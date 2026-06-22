"""Plotly bar charts for the dashboards."""
from __future__ import annotations

import pandas as pd
import plotly.express as px


def _empty(title):
    fig = px.bar(title=title)
    fig.add_annotation(text="No data", showarrow=False)
    return fig


def bar(df: pd.DataFrame, x: str, y: str, title: str, top: int = 10, horizontal: bool = True):
    if df is None or df.empty or x not in df.columns or y not in df.columns:
        return _empty(title)
    d = df.head(top).copy()
    if horizontal:
        d = d.iloc[::-1]  # largest on top
        fig = px.bar(d, x=y, y=x, orientation="h", title=title, text=y)
    else:
        fig = px.bar(d, x=x, y=y, title=title, text=y)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=max(320, 28 * len(d)),
                      yaxis_title="", xaxis_title="")
    fig.update_traces(texttemplate="%{text:,.0f}" if d[y].dtype.kind in "if" else "%{text}",
                      textposition="outside")
    return fig
