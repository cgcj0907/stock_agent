"""M4 估值方法库：纯函数、确定性、可测试（每股价值，单位：元）。

方法：DCF(可换现金化利润基数) / 唐朝估值法 / 格雷厄姆数 / 格雷厄姆公式 / DDM /
相对中位 PE / PEG。
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


# 现金化比率夹逼区间：OCF/净利 的正常区间（0.5~1.5），防止一次性损益把 DCF 基数拉爆/打穿
CASH_RATIO_LOW, CASH_RATIO_HIGH = 0.5, 1.5


def cash_earnings_proxy(
    eps: float | None,
    ocf_to_np: float | None = None,
    ocfps: float | None = None,
) -> float | None:
    """现金化利润代理：DCF 的盈利基数，避免直接用 EPS（利润≠现金）。

    优先级（与当前数据库 financials 表可用字段对齐）：
    1. `ocf_to_np × EPS`（比值先夹逼到 [0.5, 1.5]，防一次性损益失真）
    2. `ocfps`（每股经营现金流，AkShare 当前有值；DB 的 ocf_to_np 列为空时用它）
    3. 兜底 EPS 本身（无现金流字段时保持原行为，置信度相应降低）
    """
    if eps is None or eps <= 0:
        return None
    if ocf_to_np is not None:
        ratio = min(max(ocf_to_np, CASH_RATIO_LOW), CASH_RATIO_HIGH)
        return round(eps * ratio, 4)
    if ocfps is not None and ocfps > 0:
        return round(float(ocfps), 4)
    return round(float(eps), 4)


def _dcf_value(base: float, g: float, r: float, terminal_g: float, years: int) -> float | None:
    """两阶段 DCF 纯值计算：前 years 年按 g 增长，终值按 terminal_g 永续。"""
    if base is None or base <= 0 or r <= terminal_g:
        return None
    pv = 0.0
    for t in range(1, years + 1):
        fcf = base * (1 + g) ** t
        pv += fcf / (1 + r) ** t
    fcf_terminal = base * (1 + g) ** years
    tv = fcf_terminal * (1 + terminal_g) / (r - terminal_g)
    return pv + tv / (1 + r) ** years


def dcf(
    eps: float,
    g: float,
    r: float,
    terminal_g: float,
    years: int = 10,
    cash_eps: float | None = None,
) -> MethodResult:
    """两阶段 DCF（含敏感性：增速±2pct、折现率∓1pct）。

    cash_eps：现金化利润代理（ocf_to_np×EPS 或 OCFPS），非 None 时作为盈利基数；
    为 None 或 ≤0 时跳过 DCF（经营现金流为负不适合现金流折现）。
    """
    base = cash_eps if cash_eps is not None else eps
    mid = _dcf_value(base, g, r, terminal_g, years)
    if mid is None:
        if cash_eps is not None and (cash_eps <= 0):
            return MethodResult("dcf", None, note="现金化利润代理 ≤0（经营现金流为负），DCF 不适用")
        if base is None or base <= 0:
            return MethodResult("dcf", None, note="缺 EPS 或折现率 r ≤ 永续增速")
        return MethodResult("dcf", None, note="折现率 r ≤ 永续增速，DCF 不适用")
    low = _dcf_value(base, max(g - 0.02, 0.0), r + 0.01, terminal_g, years)
    high = _dcf_value(base, g + 0.02, max(r - 0.01, terminal_g + 0.01), terminal_g, years)
    params: dict = {"g": g, "r": r, "terminal_g": terminal_g, "years": years}
    if cash_eps is not None:
        params.update({"profit_base": "cash_proxy", "cash_eps": round(cash_eps, 2), "eps": round(eps, 2)})
    return MethodResult(
        "dcf",
        round(mid, 2),
        round(low, 2) if low else None,
        round(high, 2) if high else None,
        params,
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


def peg(eps: float, g: float, pe_history: list[float]) -> MethodResult:
    """PEG（费雪/彼得·林奇）：合理 PE ≈ 增速百分数（增速 15% → PE 15），价值 = EPS × 合理PE。

    只适用于有真实增速与 PE 历史的成长型公司；增速 ≤0 或缺 PE 历史时跳过。
    """
    if eps is None or eps <= 0:
        return MethodResult("peg", None, note="缺 EPS")
    if g is None or g <= 0:
        return MethodResult("peg", None, note="增速 ≤0，PEG 不适用")
    if not pe_history:
        return MethodResult("peg", None, note="缺 PE 历史")
    g_pct = g * 100
    fair_pe = g_pct  # 增速 15% → PE 15 合理
    median_pe = statistics.median(pe_history)
    peg_ratio = round(median_pe / g_pct, 2)
    return MethodResult(
        "peg", round(eps * fair_pe, 2),
        params={
            "fair_pe": round(fair_pe, 1),
            "g_pct": g_pct,
            "median_pe": round(median_pe, 2),
            "peg_ratio": peg_ratio,
        },
        note=(
            f"当前中位 PE {median_pe:.1f} 高于 PEG 合理水平（PEG={peg_ratio}）"
            if peg_ratio > 1.5 else ""
        ),
    )
