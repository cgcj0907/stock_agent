"""模块引擎 PIT 评分（docs/12-v2-upgrade.md §8.1 backlog）：M1→M2→M4 引擎链产出组合分。

与简化 `pit_score` 的区别：
- 质量分来自 **M2 财务质量引擎**（ROE/杜邦/现金流/杠杆/风险信号，分行业口径）；
- 估值分来自 **M4 估值引擎**（按生意类型路由方法 → 内在价值 vs 现价的便宜度）；
- 生意类型来自 **M1 规则分类**（快照无 industry → 按财务特征兜底）。

纯确定性、无 LLM——用于回测「规则评分流水线」的选股区分度（PIT 防前视由
`run_backtest` + `create_snapshot` 保证）；校准 A/B（规则 vs 规则+LLM）见 calibration_ab.py。
"""
from __future__ import annotations

from value_agent.business_model.engine import analyze_business_model
from value_agent.financials.quality import analyze_financial_quality
from value_agent.valuation.engine import run_valuation

# 组合权重：质量 50% + 估值便宜度 50%
_W_QUALITY = 0.5
_W_VALUE = 0.5


def _annual_records(financials: list[dict]) -> list[dict]:
    return sorted(
        (r for r in financials if str(r.get("period", "")).endswith("1231")),
        key=lambda r: str(r.get("period", "")),
    )


def _latest_close(daily: list[dict]) -> float | None:
    recs = sorted(
        (r for r in daily if r.get("close") is not None),
        key=lambda r: str(r.get("trade_date", "")), reverse=True,
    )
    return recs[0]["close"] if recs else None


def _latest_dividend(dividends: list[dict]) -> float | None:
    recs = sorted(
        (r for r in dividends if r.get("cash_div_tax") is not None),
        key=lambda r: str(r.get("trade_date", "")), reverse=True,
    )
    return recs[0]["cash_div_tax"] if recs else None


def cheapness_score(mid: float | None, price: float | None) -> float:
    """内在价值/现价 → 0-100 便宜度（≥1.2 → 80，≤0.8 → 20，中间线性）。"""
    if mid is None or price is None or price <= 0:
        return 50.0  # 无估值 → 中性（不奖励也不惩罚）
    ratio = mid / price
    if ratio >= 1.2:
        return 80.0
    if ratio <= 0.8:
        return 20.0
    return round(50.0 + (ratio - 1.0) / 0.4 * 30.0, 1)


def module_pit_score(snapshot: dict) -> float:
    """快照 → 组合分（M1 分类 → M2 质量 + M4 估值便宜度）。"""
    tables = snapshot.get("tables", {})
    annual = _annual_records(tables.get("financials", []))
    if not annual:
        return 0.0

    # M1：规则分类（快照无 industry → 空行业，按财务特征兜底）
    bm = analyze_business_model(
        {"industry": "", "name": snapshot.get("code", "")},
        {"records": annual},
    )

    # M2：财务质量（分行业口径）
    fq = analyze_financial_quality(
        annual,
        business_type=bm.business_type,
        financial_subtype=bm.financial_subtype,
    )

    # M4：估值引擎（方法路由 + 内在价值）
    latest = annual[-1]
    val = sorted(
        (r for r in tables.get("valuation_history", []) if r.get("pe_ttm")),
        key=lambda r: str(r.get("trade_date", "")), reverse=True,
    )
    pe_history = [r["pe_ttm"] for r in val if r.get("pe_ttm") and r["pe_ttm"] > 0]
    pb_history = [r["pb"] for r in val if r.get("pb") and r["pb"] > 0]
    vr = run_valuation(
        eps=latest.get("eps"),
        bvps=latest.get("bvps"),
        pe_history=pe_history,
        dividend=_latest_dividend(tables.get("dividends", [])),
        business_type=bm.business_type,
        ocfps=latest.get("ocfps"),
        ocf_to_np=latest.get("ocf_to_np"),
        debt_to_assets=latest.get("debt_to_assets"),
        eps_history=[r["eps"] for r in annual if r.get("eps") and r["eps"] > 0],
        pb_history=pb_history,
        roe=latest.get("roe"),
        ncav_ps=latest.get("ncav_ps"),
        financial_subtype=bm.financial_subtype,
    )
    mid = (vr.intrinsic or {}).get("mid")
    cheap = cheapness_score(mid, _latest_close(tables.get("daily_price", [])))

    score = _W_QUALITY * (fq.score or 0.0) + _W_VALUE * cheap
    return round(min(100.0, max(0.0, score)), 1)
