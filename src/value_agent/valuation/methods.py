"""M4 估值方法库：纯函数、确定性、可测试（每股价值，单位：元）。

方法：DCF / 唐朝估值法 / 格雷厄姆数 / 格雷厄姆公式 / DDM / 相对中位 PE。
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


@dataclass
class MethodResult:
    name: str
    value: float | None  # 每股内在价值（元），None=不适用/数据缺失
    low: float | None = None
    high: float | None = None
    params: dict = field(default_factory=dict)
    note: str = ""


def _dcf_value(eps: float, g: float, r: float, terminal_g: float, years: int) -> float | None:
    """两阶段 DCF 纯值计算：前 years 年按 g 增长，终值按 terminal_g 永续。"""
    if eps is None or eps <= 0 or r <= terminal_g:
        return None
    pv = 0.0
    for t in range(1, years + 1):
        fcf = eps * (1 + g) ** t
        pv += fcf / (1 + r) ** t
    fcf_terminal = eps * (1 + g) ** years
    tv = fcf_terminal * (1 + terminal_g) / (r - terminal_g)
    return pv + tv / (1 + r) ** years


def dcf(eps: float, g: float, r: float, terminal_g: float, years: int = 10) -> MethodResult:
    """两阶段 DCF（含敏感性：增速±2pct、折现率∓1pct）。"""
    mid = _dcf_value(eps, g, r, terminal_g, years)
    if mid is None:
        return MethodResult("dcf", None, note="缺 EPS 或折现率 r ≤ 永续增速")
    low = _dcf_value(eps, max(g - 0.02, 0.0), r + 0.01, terminal_g, years)
    high = _dcf_value(eps, g + 0.02, max(r - 0.01, terminal_g + 0.01), terminal_g, years)
    return MethodResult(
        "dcf",
        round(mid, 2),
        round(low, 2) if low else None,
        round(high, 2) if high else None,
        {"g": g, "r": r, "terminal_g": terminal_g, "years": years},
    )


def tang(eps: float, g: float, risk_free: float) -> MethodResult:
    """唐朝估值法：三年后合理估值 = EPS×(1+g)³ × (1/无风险利率)；买点50% / 卖点 min(150%, 当年净利×50)。"""
    if eps is None or eps <= 0 or risk_free <= 0:
        return MethodResult("tang", None, note="缺 EPS 或无风险利率")
    pe_fair = 1 / risk_free
    eps3 = eps * (1 + g) ** 3
    fair = eps3 * pe_fair
    buy = fair * 0.5
    sell = min(fair * 1.5, eps * 50)
    return MethodResult(
        "tang", round(fair, 2),
        params={"fair_pe": round(pe_fair, 1), "eps3": round(eps3, 2), "buy": round(buy, 2), "sell": round(sell, 2)},
    )


def graham_number(eps: float, bvps: float) -> MethodResult:
    """格雷厄姆数：√(22.5 × EPS × 每股净资产)。"""
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return MethodResult("graham_number", None, note="缺 EPS 或每股净资产")
    return MethodResult("graham_number", round(math.sqrt(22.5 * eps * bvps), 2), params={"bvps": round(bvps, 2)})


def graham_formula(eps: float, g: float, risk_free: float) -> MethodResult:
    """格雷厄姆公式：V = EPS × (8.5 + 2g%) × 4.4 / Y%。"""
    if eps is None or eps <= 0:
        return MethodResult("graham_formula", None, note="缺 EPS")
    g_pct, y_pct = g * 100, risk_free * 100
    return MethodResult(
        "graham_formula", round(eps * (8.5 + 2 * g_pct) * 4.4 / y_pct, 2),
        params={"g_pct": g_pct, "y_pct": y_pct},
    )


def ddm(div: float, g: float, r: float) -> MethodResult:
    """DDM：P = D₁/(r−g)。"""
    if div is None or div <= 0:
        return MethodResult("ddm", None, note="无分红数据")
    if r <= g:
        return MethodResult("ddm", None, note=f"折现率 r({r:.2f}) 需大于增速 g({g:.2f})")
    return MethodResult("ddm", round(div * (1 + g) / (r - g), 2), params={"div": div})


def relative_median_pe(eps: float, pe_history: list[float]) -> MethodResult:
    """相对估值：合理价 = EPS × PE 历史中位数。"""
    if eps is None or not pe_history:
        return MethodResult("relative_median_pe", None, note="缺 EPS 或 PE 历史")
    median = statistics.median(pe_history)
    return MethodResult(
        "relative_median_pe", round(eps * median, 2),
        params={"median_pe": round(median, 2), "n": len(pe_history)},
    )
