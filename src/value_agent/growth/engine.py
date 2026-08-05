"""M3 成长与再投资引擎：历史 EPS 增速 + 再投资质量 + 景气度评级（确定性规则）。"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from value_agent.financials.quality import annual_records

WACC = 0.10  # 再投资质量参照


@dataclass
class GrowthResult:
    growth_estimate: float  # 历史 EPS CAGR（有界 0~20%，供 M4 DCF 使用）
    prosperity: str         # 上行 / 平稳 / 下行
    prosperity_code: str    # up | flat | down（契约 handoff，§4 M3）
    growth_confidence: str  # high | medium | low（数据充分性）
    cyclicality_flag: bool  # ROE 波动大（CV>0.3）视为周期特征 → M4 保守
    score: float
    evidence: list[str] = field(default_factory=list)


def _eps_cagr(eps_by_year: list[tuple[int, float]]) -> float | None:
    if len(eps_by_year) < 2:
        return None
    first_year, first = eps_by_year[0]
    last_year, last = eps_by_year[-1]
    if first <= 0 or last <= 0 or last_year <= first_year:
        return None
    return (last / first) ** (1 / (last_year - first_year)) - 1


def assess_growth(financials: dict, default_growth: float = 0.10) -> GrowthResult:
    recs = sorted(
        (r for r in financials.get("records", []) if r.get("period") and r.get("eps")),
        key=lambda r: r["period"],
    )
    recs = sorted(annual_records(recs), key=lambda r: r["period"])  # 年度 EPS 算 CAGR
    eps_by_year = []
    for r in recs:
        try:
            year = int(r["period"][:4])
        except (ValueError, IndexError):
            continue
        eps_by_year.append((year, r["eps"]))

    if eps_by_year:
        cagr = _eps_cagr(eps_by_year)
        growth = max(0.0, min(cagr if cagr is not None else default_growth, 0.20))
        note = f"历史 EPS CAGR ≈ {cagr * 100:.1f}%（{eps_by_year[0][0]}→{eps_by_year[-1][0]}）" if cagr is not None else "EPS 数据不足，用默认增速"
    else:
        growth, note = default_growth, "无 EPS 数据，用默认增速"

    roe = [r["roe"] for r in recs if r.get("roe") is not None]
    debt = [r["debt_to_assets"] for r in recs if r.get("debt_to_assets") is not None]
    eps_vals = [e for _, e in eps_by_year]

    # 景气度：由增速与 ROE 趋势共同判定
    if growth >= 0.15:
        prosperity = "上行"
    elif growth >= 0.05 and (not roe or roe[-1] >= 10):
        prosperity = "平稳"
    else:
        prosperity = "下行"
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
        score += 30.0 if roe_latest >= 2 * WACC else 20.0 if roe_latest >= WACC else 8.0
    if debt:
        score += 15.0 if debt[-1] <= 0.4 else 10.0 if debt[-1] <= 0.6 else 5.0
    if len(eps_vals) >= 3 and statistics.stdev(eps_vals) / abs(statistics.mean(eps_vals)) <= 0.2:
        score += 15.0

    evidence = [
        note,
        f"增速假设：{growth:.1%}（M4 DCF 将采用）",
        f"再投资质量：ROE {roe_latest}% vs WACC {WACC:.0%}" if roe_latest is not None else "再投资质量：缺 ROE",
        f"景气度评级：{prosperity}",
    ]
    return GrowthResult(
        growth_estimate=round(growth, 4), prosperity=prosperity,
        prosperity_code=prosperity_code, growth_confidence=growth_confidence,
        cyclicality_flag=cyclicality_flag,
        score=round(min(score, 100.0), 1), evidence=evidence,
    )
