"""校准 A/B 分析测试（docs/12-v2-upgrade.md §8）：抽取 / 前向收益 / 区分度对比 / 数据驱动开关。"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from value_agent.backtest.calibration_ab import (
    CalibrationSample,
    add_months,
    analyze,
    extract_samples,
    forward_return,
    spearman,
    suggest_config,
)
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus


def _session(code: str, calibration: dict | None, *, module: str = "M5_moat") -> Session:
    session = Session(company_code=code, status=SessionStatus.COMPLETED)
    session.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    session.module_results[module] = ModuleResult(
        module=module, status=ModuleStatus.DONE, score=calibration["final"] if calibration else 50.0,
        calibration=calibration,
    )
    return session


def _sample(base: float, final: float, *, forward: float | None, outcome: str = "applied",
            delta: float | None = None, module: str = "M5_moat") -> CalibrationSample:
    return CalibrationSample(
        code="600519", module_id=module, as_of="20260101", base=base, final=final,
        outcome=outcome, delta=delta if delta is not None else final - base, forward=forward,
    )


# ---------- 抽取 ----------
def test_extract_samples_filters_disabled_and_keeps_applied():
    sessions = [
        _session("600519", {"module_id": "M5_moat", "base": 70.0, "final": 75.0,
                            "outcome": "applied", "delta": 5.0}),
        _session("600519", {"module_id": "M5_moat", "base": 70.0, "final": 70.0,
                            "outcome": "disabled", "delta": None}, module="M2_financial_quality"),
        _session("600519", None),
    ]
    samples = extract_samples(sessions)
    assert len(samples) == 1
    assert samples[0].module_id == "M5_moat"
    assert samples[0].base == 70.0 and samples[0].final == 75.0
    assert samples[0].as_of == "20260101"


def test_extract_samples_skips_non_numeric_calibration():
    session = _session("600519", {"module_id": "M5_moat", "base": None, "final": 75.0,
                                  "outcome": "applied", "delta": None})
    assert extract_samples([session]) == []


# ---------- 前向收益 ----------
def test_forward_return_window():
    daily = [
        {"trade_date": "20260101", "close": 10.0},
        {"trade_date": "20260201", "close": 11.0},
        {"trade_date": "20260630", "close": 12.0},
        {"trade_date": "20260701", "close": 12.5},   # 恰好 6 个月窗口末
        {"trade_date": "20260801", "close": 13.0},   # 窗口外
    ]
    assert forward_return(daily, "20260101", 6) == 0.25  # 12.5/10 - 1


def test_forward_return_insufficient_data():
    daily = [{"trade_date": "20260101", "close": 10.0}, {"trade_date": "20260201", "close": 11.0}]
    assert forward_return(daily, "20260101", 6) is None


def test_add_months_year_boundary():
    assert add_months("20251101", 2) == "20260101"
    assert add_months("20260101", 6) == "20260701"


def test_spearman_perfect_positive_and_reversed():
    xs = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
    ys = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
    assert spearman(xs, ys) == 1.0
    assert spearman(list(reversed(xs)), ys) == -1.0


# ---------- A/B 对比 ----------
_FWD = [i / 100 for i in range(10)]  # 严格递增的前向收益
_BASE_ASC = [float(i * 10) for i in range(10)]        # 与 forward 正相关（规则区分度好）
_BASE_DESC = [float((9 - i) * 10) for i in range(10)]  # 与 forward 负相关（规则区分度差）


def test_analyze_calibration_improves_correlation():
    samples = [
        _sample(_BASE_DESC[i], _BASE_ASC[i], forward=_FWD[i]) for i in range(10)
    ]
    rep = analyze(samples)["M5_moat"]
    assert rep.rule_corr < 0 and rep.calib_corr > 0
    assert rep.corr_gain > 0
    # 相关为正增益 → 不会走到「建议关闭」分支（delta 偏大时可能提示收紧 cap）
    assert "enabled: false" not in rep.recommendation


def test_analyze_calibration_worsens_correlation_suggests_disable():
    samples = [
        _sample(_BASE_ASC[i], _BASE_DESC[i], forward=_FWD[i]) for i in range(10)
    ]
    rep = analyze(samples)["M5_moat"]
    assert rep.corr_gain < -0.05
    assert "enabled: false" in rep.recommendation
    assert suggest_config({"M5_moat": rep})["M5_moat"] == {"enabled": False}


def test_analyze_large_abs_delta_suggests_tighter_cap():
    samples = [_sample(50.0, 65.0, forward=0.1) for _ in range(10)]
    rep = analyze(samples)["M5_moat"]
    assert rep.mean_abs_delta == 15.0
    assert "收紧 cap" in rep.recommendation
    assert suggest_config({"M5_moat": rep})["M5_moat"]["cap"] == 15.0


def test_analyze_insufficient_samples_keeps_status():
    samples = [_sample(50.0, 55.0, forward=0.1) for _ in range(3)]
    rep = analyze(samples)["M5_moat"]
    assert "样本不足" in rep.recommendation
    assert suggest_config({"M5_moat": rep}) == {}


def test_analyze_neutral_delta_keeps_status():
    samples = [_sample(50.0, 50.0, forward=0.1, delta=0.0) for _ in range(10)]
    rep = analyze(samples)["M5_moat"]
    assert rep.mean_abs_delta == 0.0
    assert "保持现状" in rep.recommendation


# ---------- 档位翻转 ----------
def test_analyze_counts_band_flips():
    samples = [
        _sample(78.0, 83.0, forward=0.1),   # watch → strong（抬分跨档）
        _sample(82.0, 74.0, forward=0.1),   # strong → watch（压分跨档）
        _sample(70.0, 71.0, forward=0.1),   # 同档（watch）不翻
        _sample(78.0, 78.0, forward=0.1, delta=0.0),  # 无移动不翻
    ]
    rep = analyze(samples)["M5_moat"]
    assert rep.up_flips == 1
    assert rep.down_flips == 1
    assert rep.band_flip_rate == pytest.approx(0.667)  # 3 个移动样本中 2 次翻档（保留 3 位）


def test_replay_end_to_end(tmp_path):
    """脚本数据流：SqliteStore 会话语料 + market.db 行情 → 抽取 → 前向收益 → 报告。"""
    from value_agent.data.storage.sqlite_storage import SqliteMarketStorage
    from value_agent.sessions import SqliteStore

    store = SqliteStore(str(tmp_path / "sessions.db"))
    session = _session("600519", {"module_id": "M5_moat", "base": 70.0, "final": 75.0,
                                  "outcome": "applied", "delta": 5.0})
    session.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    store.save(session)

    samples = extract_samples(store.list())
    assert len(samples) == 1

    mkt = SqliteMarketStorage(str(tmp_path / "m.db"))
    mkt.upsert("daily_price", "600519", [
        {"trade_date": "20250101", "close": 10.0},
        {"trade_date": "20250701", "close": 12.0},
    ])
    samples[0].forward = forward_return(mkt.records_before("daily_price", "600519"),
                                        samples[0].as_of, 6)
    assert samples[0].forward == 0.2  # 12/10 - 1（20250701 恰在 6 个月窗口末）

    reports = analyze(samples)
    assert "M5_moat" in reports
