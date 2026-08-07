"""M3 成长与再投资引擎：历史 EPS 增速 + 再投资质量 + 景气度评级（确定性规则）。

backlog 2026-08-07 落地：
- 4.6  WACC 参数化：assess_growth 接受 wacc 参数（默认 0.10），再投资质量对比口径可调。
- 4.7  CAGR 端点敏感性：多年几何平均（逐年增速几何均值），不再只用首尾两年。
- 4.8  ROE/负债率与 EPS 解耦：roe/debt 字段池独立过滤，不再以「有 EPS」为前提。
- 4.4  增速情景区间（保守/中性/乐观）+ 增长确定性评级，供 M4 DCF 用保守档参数。
"""
from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import dataclass, field

from value_agent.financials.quality import annual_records

WACC = 0.10  # 再投资质量参照（可被 wacc 参数覆盖，4.6）


@dataclass
class GrowthResult:
    growth_estimate: float  # 历史 EPS CAGR（有界 0~20%，供 M4 DCF 使用）
    prosperity: str         # 上行 / 平稳 / 下行
    prosperity_code: str    # up | flat | down（契约 handoff，§4 M3）
    growth_confidence: str  # high | medium | low（数据充分性）
    cyclicality_flag: bool  # ROE 波动大（CV>0.3）视为周期特征 → M4 保守
    score: float
    evidence: list[str] = field(default_factory=list)
    # 4.4：增速情景区间（保守/中性/乐观），M4 DCF 采用保守档
    scenarios: dict = field(default_factory=lambda: {
        "conservative": None, "neutral": None, "optimistic": None,
    })


def _eps_cagr(eps_by_year: list[tuple[int, float]]) -> float | None:
    """4.7：多年几何平均增速（逐年 YoY 的几何均值），抗端点异常。

    每年增速 g_t = eps_t / eps_{t-1} - 1，几何均值 = (∏(1+g_t))^(1/n) - 1。
    任一基期非正或持平→退化用首尾口径；样本 <2 返回 None。
    """
    if len(eps_by_year) < 2:
        return None
    # 首尾口径兜底（保留原语义）
    first_year, first = eps_by_year[0]
    last_year, last = eps_by_year[-1]
    if first <= 0 or last <= 0 or last_year <= first_year:
        return None
    ratios = []
    for (py, pv), (cy, cv) in itertools.pairwise(eps_by_year):
        if pv <= 0 or cv <= 0 or cy <= py:
            continue
        ratios.append((cv / pv) ** (1 / (cy - py)))
    if ratios:
        geo = math.prod(ratios) ** (1 / len(ratios)) - 1
        # 与首尾口径交叉校验：差异过大（>10pct）取更保守（较小者），避免被基期年异常放大
        endpoint = (last / first) ** (1 / (last_year - first_year)) - 1
        if abs(geo - endpoint) > 0.10:
            return min(geo, endpoint)
        return geo
    return (last / first) ** (1 / (last_year - first_year)) - 1


def _growth_scenarios(growth: float, confidence: str) -> dict:
    """4.4：增速情景区间。保守档 = 中性档 ×0.6；乐观档 = min(20%, 中性 +5pct)。

    信心低时保守档再下修（0.5×）。
    """
    neutral = growth
    if confidence == "low":
        conservative = max(0.0, round(neutral * 0.5, 4))
    else:
        conservative = max(0.0, round(neutral * 0.6, 4))
    optimistic = round(min(0.20, neutral + 0.05), 4)
    return {
        "conservative": conservative,
        "neutral": neutral,
        "optimistic": optimistic,
    }


def assess_growth(
    financials: dict,
    default_growth: float = 0.10,
    wacc: float = WACC,
) -> GrowthResult:
    # 4.8：字段池独立过滤——recs 只要 period；EPS / ROE / 负债率各自按有无取值
    recs = sorted(
        (r for r in financials.get("records", []) if r.get("period")),
        key=lambda r: r["period"],
    )
    annual = sorted(annual_records(recs), key=lambda r: r["period"])
    eps_by_year = []
    for r in annual:
        if r.get("eps") is None:
            continue
        try:
            year = int(r["period"][:4])
        except (ValueError, IndexError):
            continue
        eps_by_year.append((year, r["eps"]))
    # 4.8：ROE/负债率从全部年报取，不再依赖「有 EPS 的记录」
    roe = [r["roe"] for r in annual if r.get("roe") is not None]
    debt = [r["debt_to_assets"] for r in annual if r.get("debt_to_assets") is not None]
    eps_vals = [e for _, e in eps_by_year]

    cagr = None  # 无 EPS 时保持 None：增速/可信度/景气判定统一走缺省分支，避免 UnboundLocalError
    if eps_by_year:
        cagr = _eps_cagr(eps_by_year)
        growth = max(0.0, min(cagr if cagr is not None else default_growth, 0.20))
        note = f"历史 EPS CAGR ≈ {cagr * 100:.1f}%（{eps_by_year[0][0]}→{eps_by_year[-1][0]}，多年几何均值）" if cagr is not None else "EPS 数据不足，用默认增速"
    else:
        growth, note = default_growth, "无 EPS 数据，用默认增速"

    # 景气度：负增长或 ROE 显著恶化 → 下行；高增长 → 上行；其余（含零/微增长）→ 平稳。
    # 注意 growth 已被钳制到 ≥0，负 CAGR 需用原始 cagr 判断；成熟稳定公司不再误判"下行"。
    down_reason = None
    if cagr is not None and cagr < 0:
        prosperity = "下行"
        down_reason = f"EPS CAGR {cagr * 100:.1f}% 为负"
    elif growth >= 0.15:
        prosperity = "上行"
    elif len(roe) >= 2 and roe[-1] < roe[-2] - 5:
        prosperity = "下行"
        down_reason = f"ROE 同比下滑 {roe[-2] - roe[-1]:.0f}pp"
    else:
        prosperity = "平稳"
    prosperity_code = {"上行": "up", "平稳": "flat", "下行": "down"}[prosperity]

    # 增速可信度：真实 CAGR 且样本充足 → high；数据不足/默认值 → low
    if cagr is not None and len(eps_by_year) >= 3:
        growth_confidence = "high"
    elif cagr is not None and len(eps_by_year) >= 2:
        growth_confidence = "medium"
    else:
        growth_confidence = "low"

    # 周期特征代理：ROE 波动大（CV>0.3）→ 视为周期（供 M4 禁用 DCF/唐朝）
    if len(roe) >= 3 and abs(statistics.mean(roe)) > 0:
        cv = statistics.stdev(roe) / abs(statistics.mean(roe))
        cyclicality_flag = cv > 0.3
    else:
        cyclicality_flag = False

    # 评分：增速 40 + 再投资质量 30 + 财务空间 15 + 稳定性 15
    score = 40.0 if growth >= 0.15 else 35.0 if growth >= 0.10 else 25.0 if growth >= 0.05 else 12.0
    roe_latest = roe[-1] if roe else None
    if roe_latest is not None:
        score += 30.0 if roe_latest >= 2 * wacc else 20.0 if roe_latest >= wacc else 8.0
    if debt:
        score += 15.0 if debt[-1] <= 0.4 else 10.0 if debt[-1] <= 0.6 else 5.0
    if len(eps_vals) >= 3 and statistics.stdev(eps_vals) / abs(statistics.mean(eps_vals)) <= 0.2:
        score += 15.0

    scenarios = _growth_scenarios(growth, growth_confidence)
    evidence = [
        note,
        f"增速假设：{growth:.1%}（M4 DCF 将采用）",
        f"增速情景：保守 {scenarios['conservative']:.1%} / 中性 {growth:.1%} / 乐观 {scenarios['optimistic']:.1%}",
        f"再投资质量：ROE {roe_latest}% vs WACC {wacc:.0%}" if roe_latest is not None else "再投资质量：缺 ROE",
        f"景气度评级：{prosperity}" + (f"（{down_reason}）" if down_reason else ""),
    ]
    return GrowthResult(
        growth_estimate=round(growth, 4), prosperity=prosperity,
        prosperity_code=prosperity_code, growth_confidence=growth_confidence,
        cyclicality_flag=cyclicality_flag,
        score=round(min(score, 100.0), 1), evidence=evidence,
        scenarios=scenarios,
    )
