"""分红数据解析单元测试（纯函数，不依赖网络）：过滤/换算/排序。"""
from __future__ import annotations

import pandas as pd

from value_agent.data.sources.akshare_source import _dividend_records_from_df


def _df():
    return pd.DataFrame([
        {"报告期": "2025-12-31", "现金分红-现金分红比例": 280.242, "方案进度": "实施分配"},
        {"报告期": "2025-09-30", "现金分红-现金分红比例": 239.57, "方案进度": "实施分配"},
        {"报告期": "2026-06-30", "现金分红-现金分红比例": float("nan"), "方案进度": "预披露"},
        {"报告期": "2026-03-31", "现金分红-现金分红比例": 100.0, "方案进度": "股东大会通过"},
        {"报告期": "2001-12-31", "现金分红-现金分红比例": 6.0, "方案进度": "实施分配"},
    ])


def test_filters_unimplemented_and_nan():
    recs = _dividend_records_from_df(_df())
    assert [r["period"] for r in recs] == ["20251231", "20250930", "20011231"]  # 已实施 + 倒序


def test_converts_per_10_to_per_share():
    recs = _dividend_records_from_df(_df())
    assert recs[0]["cash_div_tax"] == 28.0242  # 280.242 / 10
    assert recs[2]["cash_div_tax"] == 0.6  # 6.0 / 10
    assert all(r["cash_div_tax"] > 0 for r in recs)


def test_period_format_valid_for_validate():
    from value_agent.data.validate import validate_dividends

    report = validate_dividends(_dividend_records_from_df(_df()))
    assert report.valid == report.total == 3
