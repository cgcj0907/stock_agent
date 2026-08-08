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


def tang(eps: float, g: float, risk_free: float, *, pe_cap: float | None = None) -> MethodResult:
    """唐朝估值法：三年后合理估值 = EPS×(1+g)³ × (1/无风险利率)；买点50% / 卖点 min(150%, 当年净利×50)。

    pe_cap：合理 PE 上限（如公用事业类 18 倍），避免低无风险利率下 1/rf 把估值拉高。
    """
    if eps is None or eps <= 0 or risk_free <= 0:
        return MethodResult("tang", None, note="缺 EPS 或无风险利率")
    pe_fair = 1 / risk_free
    if pe_cap is not None:
        pe_fair = min(pe_fair, pe_cap)
    eps3 = eps * (1 + g) ** 3
    fair = eps3 * pe_fair
    buy = fair * 0.5
    sell = min(fair * 1.5, eps * 50)
    return MethodResult(
        "tang", round(fair, 2),
        params={"fair_pe": round(pe_fair, 1), "pe_cap": pe_cap, "eps3": round(eps3, 2), "buy": round(buy, 2), "sell": round(sell, 2)},
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


# DDM 最小折现率-增速价差：价差过小（如 r=8%/g=6%）时分母趋零、价值爆炸，直接跳过
DDM_MIN_SPREAD = 0.02


def ddm(div: float, g: float, r: float, eps: float | None = None) -> MethodResult:
    """DDM：P = D₁/(r−g)。要求 r−g ≥ 2pct（价差过小 DDM 不稳定，跳过）。

    2.4：传 EPS 做分红覆盖校验——分红率 >100%（派息超过盈利）时标注可持续性存疑，
    价值仅作参考（低分红比例公司 DDM 会低估价值，高分红比例不可持续则高估）。
    """
    if div is None or div <= 0:
        return MethodResult("ddm", None, note="无分红数据")
    if r <= g:
        return MethodResult("ddm", None, note=f"折现率 r({r:.2f}) 需大于增速 g({g:.2f})")
    if r - g < DDM_MIN_SPREAD:
        return MethodResult(
            "ddm", None,
            note=f"折现率-增速价差 {r - g:.1%} < {DDM_MIN_SPREAD:.0%}，DDM 不稳定，跳过",
        )
    note = ""
    payout = None
    if eps is not None and eps > 0:
        payout = round(div / eps, 3)
        if payout > 1.0:
            note = f"⚠️ 分红率 {payout:.0%} >100%（派息超过盈利），可持续性存疑，价值仅参考"
        elif payout < 0.3:
            note = f"分红率 {payout:.0%} 偏低，DDM 可能低估公司价值（配合盈利类方法交叉）"
    params: dict = {"div": div, "spread": round(r - g, 4)}
    if payout is not None:
        params["payout"] = payout
    return MethodResult("ddm", round(div * (1 + g) / (r - g), 2), params=params, note=note)


def relative_median_pe(
    eps: float,
    pe_history: list[float],
    *,
    normalized_eps: float | None = None,
    pe_cap: float | None = None,
) -> MethodResult:
    """相对估值：合理价 = PE 历史中位数 × EPS。

    normalized_eps / pe_cap：**周期股正常化保护**。周期股直接用「当期 EPS × 历史中位 PE」
    会双重失真：景气高点的当期 EPS × 被低谷年份（EPS≈0 → PE 上百）顶高的历史中位 PE，
    会把估值顶到天上去（如中国船舶：1.40 × 101 = 142 元 vs 现价 35）。
    传入 normalized_eps（近 N 年 EPS 中位数）时代替当期 EPS，并把 PE 夹逼到 pe_cap
    （默认 25），避免亏损/微利年份的异常 PE 拉高估值。
    """
    if eps is None or not pe_history:
        return MethodResult("relative_median_pe", None, note="缺 EPS 或 PE 历史")
    median_pe = statistics.median(pe_history)
    base, mode = (normalized_eps, "normalized") if normalized_eps is not None else (eps, "current")
    pe_used = min(median_pe, pe_cap) if pe_cap else median_pe  # 封顶对当期/正常化口径都生效
    if base is None or base <= 0 or pe_used <= 0:
        return MethodResult("relative_median_pe", None, note="EPS 或 PE 非正，不适用")
    return MethodResult(
        "relative_median_pe", round(base * pe_used, 2),
        params={
            "median_pe": round(median_pe, 2), "pe_used": round(pe_used, 2),
            "eps_base": mode, "n": len(pe_history),
        },
    )


def pb_band(bvps: float, pb_history: list[float]) -> MethodResult:
    """PB 估值法（周期/资产型主方法）：价值 = 每股净资产 × 历史 PB 中位；区间 = p25/p75。

    重资产/周期股盈利波动大，PE 失真，用 PB（每股净资产相对稳定）更稳。
    """
    if bvps is None or bvps <= 0 or not pb_history:
        return MethodResult("pb_band", None, note="缺每股净资产或 PB 历史")
    pbs = sorted(p for p in pb_history if p is not None and p > 0)
    if not pbs:
        return MethodResult("pb_band", None, note="PB 历史无有效值")

    def _pct(ratio: float) -> float:
        return pbs[min(len(pbs) - 1, int(len(pbs) * ratio))]

    p25, p50, p75 = _pct(0.25), _pct(0.50), _pct(0.75)
    return MethodResult(
        "pb_band",
        round(bvps * p50, 2),
        round(bvps * p25, 2),
        round(bvps * p75, 2),
        {"median_pb": round(p50, 3), "p25": round(p25, 3), "p75": round(p75, 3), "n": len(pbs)},
    )


def pb_roe(
    bvps: float,
    roe: float,
    g: float,
    r: float,
    *,
    pb_floor: float = 0.4,
    pb_cap: float = 3.0,
) -> MethodResult:
    """PB-ROE（银行/金融主方法）：V = 每股净资产 × (ROE−g)/(r−g)。

    银行盈利受拨备/杠杆影响，PE 结构性失真；PB-ROE 把「盈利能力（ROE）相对资本成本（r）
    的超额」折算成合理市净率。隐含 PB 夹逼到 [pb_floor, pb_cap] 防参数敏感爆炸。
    """
    if bvps is None or bvps <= 0:
        return MethodResult("pb_roe", None, note="缺每股净资产")
    if roe is None or roe <= 0:
        return MethodResult("pb_roe", None, note="缺 ROE 或 ROE≤0")
    if r is None or r <= g:
        return MethodResult("pb_roe", None, note="折现率需大于增速")
    implied_pb = (roe - g) / (r - g)
    implied_pb = max(pb_floor, min(pb_cap, implied_pb))
    return MethodResult(
        "pb_roe", round(bvps * implied_pb, 2),
        params={"roe": roe, "g": g, "r": r, "implied_pb": round(implied_pb, 3)},
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


def dcf_three_stage(
    eps: float,
    g: float,
    r: float,
    terminal_g: float,
    high_years: int = 5,
    decel_years: int = 5,
    cash_eps: float | None = None,
    decel_factor: float = 0.5,
) -> MethodResult:
    """三阶段 DCF（backlog 2.1，费雪视角成长股）：高速 5y + 减速 5y + 永续。

    高增长阶段按 g 增长，减速阶段按 g×decel_factor 线性衰减到永续增速，随后永续折现。
    参数保守化：高速档用 M3 增速 g（已夹逼 ≤20%），减速档默认 g×0.5，
    与两阶段 DCF 交叉验证，避免成长股单一口径外推。
    """
    base = cash_eps if cash_eps is not None else eps
    if base is None or base <= 0 or r <= terminal_g:
        if base is not None and base <= 0:
            return MethodResult("dcf_three_stage", None, note="现金化利润代理 ≤0，三阶段 DCF 不适用")
        return MethodResult("dcf_three_stage", None, note="折现率 r ≤ 永续增速，三阶段 DCF 不适用")
    decel_g = max(g * decel_factor, terminal_g)
    if decel_g >= r:
        return MethodResult("dcf_three_stage", None,
                            note=f"减速增速 {decel_g:.1%} ≥ 折现率 {r:.1%}，三阶段 DCF 不稳定，跳过")
    pv = 0.0
    fcf = base
    for t in range(1, high_years + 1):
        fcf *= 1 + g
        pv += fcf / (1 + r) ** t
    for t in range(high_years + 1, high_years + decel_years + 1):
        # 减速阶段：从 g 线性衰减到 decel_g
        frac = (t - high_years) / decel_years
        growth_t = g + (decel_g - g) * frac
        fcf *= 1 + growth_t
        pv += fcf / (1 + r) ** t
    tv = fcf * (1 + terminal_g) / (r - terminal_g)
    total = pv + tv / (1 + r) ** (high_years + decel_years)
    params = {
        "g": g, "r": r, "terminal_g": terminal_g,
        "high_years": high_years, "decel_years": decel_years,
        "decel_g": round(decel_g, 4),
    }
    if cash_eps is not None:
        params.update({"profit_base": "cash_proxy", "cash_eps": round(cash_eps, 2), "eps": round(eps, 2)})
    return MethodResult(
        "dcf_three_stage", round(total, 2),
        params=params,
        note="三阶段：高速5y+减速5y+永续（参数保守化）",
    )


def nav(bvps: float | None, discount: float = 0.80) -> MethodResult:
    """NAV 清算价值（backlog 1.1）：每股净资产 × 变现折扣。

    困境/重资产/地产公司的估值硬底线——账面净资产打折变现的底线价。
    """
    if bvps is None or bvps <= 0:
        return MethodResult("nav", None, note="缺每股净资产（BVPS）")
    return MethodResult(
        "nav", round(bvps * discount, 2),
        params={"bvps": round(bvps, 2), "liquidation_discount": discount},
        note=f"NAV：每股净资产 {bvps:.2f} × 变现折扣 {discount:.0%}",
    )


def ncav(ncav_ps: float | None, discount: float = 0.75) -> MethodResult:
    """NCAV 净流动资产价值（格雷厄姆，backlog 1.1）：每股净流动资产 × 保守折扣。

    NCAV = (流动资产 − 总负债) / 股本；格雷厄姆认为买入价应显著低于该值。
    """
    if ncav_ps is None or ncav_ps <= 0:
        return MethodResult("ncav", None, note="缺每股净流动资产（NCAV）")
    return MethodResult(
        "ncav", round(ncav_ps * discount, 2),
        params={"ncav_ps": round(ncav_ps, 2), "discount": discount},
        note=f"NCAV：每股净流动资产 {ncav_ps:.2f} × 保守折扣 {discount:.0%}",
    )
