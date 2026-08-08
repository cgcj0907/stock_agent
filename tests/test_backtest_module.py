"""模块级 PIT 评分回测测试（docs/12-v2-upgrade.md §8.1 backlog）。"""
from __future__ import annotations

import pytest

from value_agent.backtest.engine import run_backtest
from value_agent.backtest.module_score import cheapness_score, module_pit_score
from value_agent.data.storage.sqlite_storage import SqliteMarketStorage


@pytest.fixture
def storage(tmp_path):
    return SqliteMarketStorage(str(tmp_path / "m.db"))


def _seed(storage, code, *, roe, debt, eps=None, bvps=None, pe_series=None, price_series=None):
    fin = {"period": "20241231", "roe": roe, "debt_to_assets": debt,
           "grossprofit_margin": 40.0, "netprofit_margin": 20.0, "ocf_to_np": 1.0}
    if eps is not None:
        fin["eps"] = eps
    if bvps is not None:
        fin["bvps"] = bvps
    storage.upsert("financials", code, [fin])
    storage.upsert("valuation_history", code,
                   [{"trade_date": d, "pe_ttm": pe} for d, pe in (pe_series or [])])
    storage.upsert("daily_price", code,
                   [{"trade_date": d, "close": p} for d, p in (price_series or [])])


def test_cheapness_score_mapping():
    assert cheapness_score(None, 50.0) == 50.0
    assert cheapness_score(50.0, None) == 50.0
    assert cheapness_score(60.0, 50.0) == 80.0    # 1.2 倍内在价值
    assert cheapness_score(40.0, 50.0) == 20.0    # 0.8 倍
    assert cheapness_score(50.0, 50.0) == 50.0    # 平价


def test_module_pit_score_high_quality_and_cheap(storage):
    _seed(storage, "600001", roe=30, debt=0.2, eps=4.5, bvps=31.7,
          pe_series=[("20250101", 10), ("20250102", 12), ("20250103", 11)],
          price_series=[("20250101", 30.0), ("20250102", 31.0), ("20250103", 32.0)])
    snap = {"code": "600001", "tables": {
        "financials": storage.records_before("financials", "600001"),
        "valuation_history": storage.records_before("valuation_history", "600001"),
        "daily_price": storage.records_before("daily_price", "600001"),
        "dividends": [],
    }}
    score = module_pit_score(snap)
    assert score >= 70  # 高 ROE + 便宜（内在价值应显著高于现价）


def test_module_pit_score_poor_company_low(storage):
    _seed(storage, "600002", roe=3, debt=0.85, eps=0.2, bvps=5.0,
          pe_series=[("20250101", 80), ("20250102", 90)],
          price_series=[("20250101", 100.0), ("20250102", 101.0)])
    snap = {"code": "600002", "tables": {
        "financials": storage.records_before("financials", "600002"),
        "valuation_history": storage.records_before("valuation_history", "600002"),
        "daily_price": storage.records_before("daily_price", "600002"),
        "dividends": [],
    }}
    assert module_pit_score(snap) < 50


def test_run_backtest_with_module_score_fn(storage):
    """score_fn 参数：模块评分也能跑通 PIT 月度选股，并选到优质便宜股。"""
    _seed(storage, "600001", roe=30, debt=0.2, eps=4.5, bvps=31.7,
          pe_series=[("20250101", 10), ("20250102", 10), ("20250103", 10)],
          price_series=[("20250101", 30.0), ("20250102", 31.0), ("20250103", 32.0)])
    _seed(storage, "600002", roe=3, debt=0.85, eps=0.2, bvps=5.0,
          pe_series=[("20250101", 80), ("20250102", 80), ("20250103", 80)],
          price_series=[("20250101", 100.0), ("20250102", 95.0), ("20250103", 96.0)])
    r = run_backtest(storage, ["600001", "600002"], "20250101", "20250301",
                     top_n=1, score_fn=module_pit_score)
    assert r.trades[0]["picks"] == ["600001"]
    assert r.metrics["超额(策略-基准)"] > 0
