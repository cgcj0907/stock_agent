"""回测引擎单元测试：PIT 防前视 / 选股 / 指标。"""
import pytest

from value_agent.backtest.engine import pit_score, run_backtest
from value_agent.data.storage.sqlite_storage import SqliteMarketStorage


def _seed(storage, code, roe, pe_series, price_series):
    """写入一只股票：年度财报(单期) + 估值序列 + 价格序列（按日期）。"""
    storage.upsert("financials", code, [{"period": "20241231", "roe": roe, "debt_to_assets": 0.3}])
    storage.upsert("valuation_history", code, [{"trade_date": d, "pe_ttm": pe} for d, pe in pe_series])
    storage.upsert("daily_price", code, [{"trade_date": d, "close": p} for d, p in price_series])


@pytest.fixture
def storage(tmp_path):
    return SqliteMarketStorage(str(tmp_path / "m.db"))


def test_pit_score_quality_and_cheapness(storage):
    _seed(storage, "600001", roe=25, pe_series=[("20250101", 50), ("20250102", 40), ("20250103", 10)],
          price_series=[("20250101", 10), ("20250102", 11), ("20250103", 12)])
    snap_high = {"tables": {"financials": storage.records_before("financials", "600001"),
                            "valuation_history": storage.records_before("valuation_history", "600001", "20250102")}}
    score = pit_score(snap_high)
    assert score >= 80  # ROE 高 + PE 分位低


def test_snapshot_excludes_future_financials(storage):
    storage.upsert("financials", "600001", [
        {"period": "20241231", "roe": 10, "debt_to_assets": 0.3},
        {"period": "20251231", "roe": 30, "debt_to_assets": 0.2},  # 未来财报（前视）
    ])
    snap = {"tables": {"financials": storage.records_before("financials", "600001", "20250101"),
                       "valuation_history": []}}
    assert len(snap["tables"]["financials"]) == 1
    assert snap["tables"]["financials"][0]["period"] == "20241231"


def test_run_backtest_selects_and_returns(storage):
    # A 股：高质量+便宜 → 涨；B 股：差 → 跌
    _seed(storage, "600001", roe=30,
          pe_series=[("20250101", 50), ("20250102", 10), ("20250103", 10)],
          price_series=[("20250101", 100), ("20250102", 101), ("20250103", 110)])
    _seed(storage, "600002", roe=5,
          pe_series=[("20250101", 5), ("20250102", 5), ("20250103", 5)],
          price_series=[("20250101", 100), ("20250102", 90), ("20250103", 95)])
    r = run_backtest(storage, ["600001", "600002"], "20250101", "20250301", top_n=1)
    assert len(r.monthly_returns) >= 1
    assert r.trades[0]["picks"] == ["600001"]  # 选到高质量便宜股
    assert r.metrics["总收益"] > 0
    assert r.metrics["超额(策略-基准)"] > 0  # 优于等权基准


def test_metrics_fields_present(storage):
    _seed(storage, "600001", roe=20,
          pe_series=[("20250101", 20), ("20250102", 20), ("20250103", 20)],
          price_series=[("20250101", 100), ("20250102", 100), ("20250103", 100)])
    r = run_backtest(storage, ["600001"], "20250101", "20250301", top_n=1)
    for key in ("总收益", "年化收益", "最大回撤", "夏普", "胜率", "超额(策略-基准)"):
        assert key in r.metrics
