"""数据勾稽校验测试：合法/非法记录。"""
import pytest

from value_agent.data.validate import (
    validate_daily_prices,
    validate_financials,
    validate_valuation_history,
    valid_records,
)


def test_financials_valid_and_invalid():
    recs = [
        {"period": "20261231", "roe": 18.0, "grossprofit_margin": 45.0, "netprofit_margin": 25.0,
         "debt_to_assets": 0.35, "eps": 4.5, "ocf_to_np": 1.2},
        {"period": "bad", "roe": 999.0, "grossprofit_margin": -5.0, "netprofit_margin": 25.0,
         "debt_to_assets": 5.0, "eps": 0, "ocf_to_np": 1.2},
    ]
    report = validate_financials(recs)
    assert report.valid == 1
    assert report.invalid == 1
    assert "period 非 YYYYMMDD" in report.issues[0]["message"]


def test_price_high_low_consistency():
    bad = {"trade_date": "20260803", "open": 100, "close": 99, "high": 98, "low": 101, "volume": 1000}
    good = {"trade_date": "20260803", "open": 100, "close": 99, "high": 101, "low": 98, "volume": 1000}
    assert validate_daily_prices([bad]).valid == 0
    assert validate_daily_prices([good]).valid == 1


def test_valuation_pb_negative_rejected():
    recs = [{"trade_date": "20260803", "pe_ttm": -10, "pb": -1.0, "dv_ttm": 0.02}]
    assert validate_valuation_history(recs).valid == 0  # pb 为负；PE 允许负


def test_valid_records_filters():
    recs = [
        {"trade_date": "20260803", "close": 100, "volume": 1},
        {"trade_date": "20260803", "close": -5, "volume": 1},  # 无效
    ]
    valid, report = valid_records("daily_price", recs)
    assert len(valid) == 1
    assert report.invalid == 1
