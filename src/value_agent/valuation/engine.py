"""M4 估值引擎：方法路由（按生意类型）+ 多模型交叉 + 加权汇总。

业务类型默认来自 M1（当前为 stub，暂用 assumptions 覆盖），
路由表与 config/valuation_routing.yaml 一致（代码内 DEFAULT_ROUTING 为兜底默认值，
tests/test_valuation.py 锁定两者不漂移）。

v2 改动（2026-08-07，对应"大师视角下的 M4 优化"收敛版）：
- 汇总从 min/max 改为「加权中位数 ± 加权标准差」，新增 method_agreement
- 新增 valuation_confidence（方法级置信度 × 覆盖度 × 一致性）
- 新增质量乘数（M2/M3/M5/M6 分数 → 0.85~1.1 克制区间）
- 新增 kill_switch（复用 M2 风险信号 / M3 周期景气 / M5 护城河 / M6 治理，不新造信号）
- DCF 支持现金化利润代理（ocf_to_np×EPS / OCFPS，DB financials 表字段可直接取）
- 新增 PEG 方法（growth 路由启用）
- 买卖点仍归 M8（safety_margin），M4 不重复产出 buy/sell
"""
from __future__ import annotations

import logging
import math
import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

from .methods import (
    MethodResult,
    cash_earnings_proxy,
    dcf,
    dcf_three_stage,
    ddm,
    graham_formula,
    graham_number,
    nav,
    ncav,
    pb_band,
    pb_roe,
    peg,
    relative_median_pe,
    tang,
)

# 已实现方法（= methods.py 的函数名）；路由表里未实现的规划方法会被剔除，前端只展示可执行方法
IMPLEMENTED_METHODS = frozenset(
    {"dcf", "dcf_three_stage", "tang", "graham_number", "graham_formula",
     "ddm", "relative_median_pe", "peg", "pb_band", "pb_roe", "nav", "ncav"}
)

# 兜底路由（与 config/valuation_routing.yaml 对齐；M1 落地后从输入取类型）
DEFAULT_ROUTING: dict[str, list[str]] = {
    "consumer_monopoly": ["dcf", "tang", "graham_number", "graham_formula", "ddm", "relative_median_pe"],
    "growth": ["dcf", "dcf_three_stage", "peg", "relative_median_pe"],  # 费雪视角：三阶段 DCF + PEG
    "cyclical": ["relative_median_pe", "pb_band", "graham_number", "nav"],  # 禁 DCF/唐朝（周期股）；PB 主用 + NAV 资产兜底
    "financial": ["relative_median_pe", "ddm"],           # 禁 DCF（现金流法不适用）
    "asset_based": ["nav", "ncav", "graham_number", "graham_formula"],  # 1.1：清算/净流动资产底线
    "stable_dividend": ["ddm", "tang", "relative_median_pe"],
}
DEFAULT_TYPE = "consumer_monopoly"

# 方法权重（规则权重，先写死；P2 再回测反推）。权重无需归一，加权中位数只看相对大小
METHOD_WEIGHTS: dict[str, float] = {
    "dcf": 0.35,               # 现金流折现为主
    "dcf_three_stage": 0.30,   # 三阶段 DCF（成长股，2.1 参数保守化）
    "tang": 0.20,              # 唐朝/DDM 一档
    "ddm": 0.20,
    "graham_number": 0.15,     # 格雷厄姆/资产兜底一档
    "graham_formula": 0.15,
    "nav": 0.20,               # NAV/NCAV（资产型/周期资产底线，1.1）
    "ncav": 0.20,
    "relative_median_pe": 0.30,  # 相对 PE / PEG 一档
    "peg": 0.30,
    "pb_band": 0.30,           # PB 估值（周期/资产型；cyclical 里 TYPE_WEIGHTS 提到 0.50）
    "pb_roe": 0.30,            # PB-ROE（银行主方法；financial_bank 里 TYPE_WEIGHTS 提到 0.50）
}

# 质量乘数权重（对应反馈建议：0.35×M2 + 0.25×M5 + 0.2×M3 + 0.2×M6）
QUALITY_WEIGHTS: dict[str, float] = {"m2": 0.35, "m5": 0.25, "m3": 0.20, "m6": 0.20}

# 生意类型级权重覆盖（合并到 METHOD_WEIGHTS 之上）。周期股：PB 主用 + 正常化 PE 次之。
TYPE_WEIGHTS: dict[str, dict[str, float]] = {
    "cyclical": {
        "pb_band": 0.50,             # 重资产周期股主方法（PB 相对稳定）
        "relative_median_pe": 0.25,  # 正常化 EPS × 封顶 PE
        "graham_number": 0.15,       # 资产兜底
    },
    "financial_bank": {              # 银行：PB-ROE 主方法 + DDM
        "pb_roe": 0.50,
        "ddm": 0.25,
    },
    "financial_broker": {            # 券商：金融外壳、周期内核 → 等同周期股处理
        "relative_median_pe": 0.25,
        "pb_band": 0.50,
        "graham_number": 0.15,
    },
}

# 周期股正常化保护参数
CYCLICAL_PE_CAP = 25.0   # 正常化口径下合理 PE 上限（防止低谷年份 PE 顶高估值）
CYCLICAL_EPS_YEARS = 5   # 正常化 EPS = 近 N 年 EPS 中位数

# 2.3：次新股最少样本门槛——PE 历史 < 250 交易日或年报 < 3 期 → 相对估值/增速置信度降级
NEW_STOCK_PE_MIN = 250        # 交易日
NEW_STOCK_ANNUAL_MIN = 3      # 年报期数

# 2.6：格雷厄姆公式（1970s 4.4/Y 参数）仅当期 PE < 10 时启用
GRAHAM_FORMULA_MAX_PE = 10.0

# 唐朝法合理 PE 上限（按生意类型）：公用事业/类债资产用低 PE（regulated return），勿套 25 倍
TANG_PE_CAP: dict[str, float] = {"stable_dividend": 18.0}

# 金融子类型路由（financial 内部按细分行业切换方法）
FINANCIAL_SUBTYPE_ROUTES: dict[str, list[str]] = {
    "bank": ["pb_roe", "ddm"],                         # 银行：PE 被拨备扭曲，PB-ROE 标准
    "broker": ["relative_median_pe", "pb_band", "graham_number"],  # 券商：盈利强周期，等同周期股
    "insurance": ["relative_median_pe", "ddm"],        # 保险：暂用，EV 数据待接入
}
# 需正常化 EPS 保护的子类型（和周期股同病根：盈利波动大）
NORMALIZED_SUBTYPES = {"broker"}

# 方法级置信度基础值（0-1）
BASE_CONFIDENCE: dict[str, float] = {
    "dcf": 0.70,
    "tang": 0.65,
    "graham_number": 0.60,
    "graham_formula": 0.55,
    "ddm": 0.65,
    "relative_median_pe": 0.70,
    "peg": 0.60,
}


def default_params() -> dict:
    return {
        "growth_rate": 0.10,      # 保守增速（≤15% 上限见工程规范）
        "discount_rate": 0.10,    # WACC 默认
        "terminal_growth": 0.03,  # 永续增长（≤3%）
        "risk_free_rate": 0.04,   # 无风险利率（唐朝法合理PE=25）
    }


def _routing_candidates() -> list[str]:
    here = Path(__file__).resolve()
    root = here.parents[3]  # <repo>/src/value_agent/valuation/engine.py → parents[3]=<repo>
    return [str(root / "config" / "valuation_routing.yaml"), "config/valuation_routing.yaml"]


def load_routing() -> dict[str, list[str]]:
    """路由唯一事实来源 = config/valuation_routing.yaml；缺失/解析失败回退 DEFAULT_ROUTING。

    过滤掉未实现的方法（规划中方法不进入前端展示，避免"理念正确但取不到数"）。
    """
    import yaml  # type: ignore

    for path in _routing_candidates():
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            routing = {}
            for bt, meta in (raw.get("routing") or {}).items():
                methods = [
                    m for m in (meta or {}).get("methods", [])
                    if m in IMPLEMENTED_METHODS
                ]
                if methods:
                    routing[bt] = methods
            if routing:
                return routing
        except Exception:
            logger.warning("估值路由配置解析失败，使用代码兜底：%s", path, exc_info=True)
            break
    return {k: list(v) for k, v in DEFAULT_ROUTING.items()}


# ---------------- 加权统计 ----------------
def _weighted_median(values: list[float], weights: list[float]) -> float:
    """加权中位数：按值升序，累计权重首次 ≥ 半权重的点。"""
    pairs = sorted(zip(values, weights))
    total = sum(weights)
    if total <= 0:
        return statistics.median(values)
    half = total / 2.0
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= half:
            return v
    return pairs[-1][0]


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    total = sum(weights)
    return sum(v * w for v, w in zip(values, weights)) / total if total else 0.0


def _weighted_std(values: list[float], weights: list[float], mean: float) -> float:
    total = sum(weights)
    if total <= 0:
        return 0.0
    var = sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total
    return math.sqrt(max(var, 0.0))


# ---------------- 质量乘数（0.85~1.1，克制区间） ----------------
def quality_multiplier(quality: dict | None) -> tuple[float, str, float | None, list[str]]:
    """质量乘数：0.35×M2 + 0.25×M5 + 0.2×M3 + 0.2×M6 → 0.85/0.9/1.0/1.1。

    缺失的模块按剩余权重重新归一（quick 工作流只有 M2 时退化为 M2 单源）。
    """
    evidence: list[str] = []
    if not quality:
        return 1.0, "neutral", None, ["无 M2/M3/M5/M6 质量分输入，质量乘数取中性 1.0"]
    present = {k: v for k, v in quality.items() if v is not None}
    if not present:
        return 1.0, "neutral", None, ["无 M2/M3/M5/M6 质量分输入，质量乘数取中性 1.0"]
    total_w = sum(QUALITY_WEIGHTS[k] for k in present)
    q = sum(QUALITY_WEIGHTS[k] * v for k, v in present.items()) / total_w
    q = max(0.0, min(100.0, q))
    if q >= 80:
        mult, tier = 1.1, "tier_1"
    elif q >= 60:
        mult, tier = 1.0, "tier_2"
    elif q >= 40:
        mult, tier = 0.9, "tier_3"
    else:
        mult, tier = 0.85, "tier_4"
    src = "、".join(f"{k}={v:.0f}" for k, v in sorted(present.items()))
    evidence.append(f"质量分 {q:.1f}（{src}）→ 乘数 {mult}（{tier}）")
    return mult, tier, round(q, 1), evidence


# ---------------- kill switch（复用上游信号） ----------------
@dataclass
class KillSwitchResult:
    allowed: list[str]
    method_discounts: dict[str, float]
    overall_multiplier: float
    switches: list[str]
    evidence: list[str] = field(default_factory=list)


def kill_switch_check(
    allowed: list[str],
    *,
    m2_signals: list[str] | None = None,
    debt_latest: float | None = None,
    m3_cyclicality_flag: bool | None = None,
    m3_prosperity_code: str | None = None,
    m5_width: str | None = None,
    m6_score: float | None = None,
) -> KillSwitchResult:
    """kill switch：全部复用 M2/M3/M5/M6 既有输出，不新造信号。

    - LOSS_YEAR（M2）→ 禁用 DCF/唐朝/PEG（盈利外推失真）
    - OCF_NP_DIVERGENCE（M2）→ DCF 价值 ×0.85
    - 负债率 >70%（M2 财务字段）→ 整体估值 ×0.85
    - 周期特征 + 景气下行（M3）→ 只保留 PB/相对/资产估值
    - 护城河缺失（M5）+ 治理弱（M6）→ 整体估值 ×0.9
    """
    allowed = list(allowed)
    discounts: dict[str, float] = {}
    overall = 1.0
    switches: list[str] = []
    evidence: list[str] = []
    signals = set(m2_signals or [])

    if "LOSS_YEAR" in signals:
        removed = [m for m in ("dcf", "tang", "peg") if m in allowed]
        allowed = [m for m in allowed if m not in ("dcf", "tang", "peg")]
        if removed:
            switches.append("LOSS_YEAR")
            evidence.append(f"⚠️ kill_switch[LOSS_YEAR]：存在亏损年份，禁用 {'/'.join(removed)}（盈利不稳定）")

    if "OCF_NP_DIVERGENCE" in signals and "dcf" in allowed:
        discounts["dcf"] = 0.85
        switches.append("OCF_NP_DIVERGENCE")
        evidence.append("⚠️ kill_switch[OCF_NP_DIVERGENCE]：经营现金流与净利背离，DCF 价值 ×0.85")

    if debt_latest is not None and debt_latest > 0.7:
        overall *= 0.85
        switches.append("HIGH_LEVERAGE")
        evidence.append(f"⚠️ kill_switch[HIGH_LEVERAGE]：资产负债率 {debt_latest:.1%} >70%，整体估值 ×0.85")

    if m3_cyclicality_flag and m3_prosperity_code == "down":
        keep = [m for m in allowed if m in ("pb_band", "relative_median_pe", "graham_number", "graham_formula")]
        if keep:
            allowed = keep
        switches.append("CYCLICAL_DOWN")
        evidence.append("⚠️ kill_switch[CYCLICAL_DOWN]：周期特征 + 景气下行，仅保留 PB/相对/资产类估值")

    if m5_width == "none" and m6_score is not None and m6_score < 50:
        overall *= 0.9
        switches.append("NO_MOAT_POOR_GOV")
        evidence.append("⚠️ kill_switch[NO_MOAT_POOR_GOV]：护城河缺失且治理弱，整体估值 ×0.9")

    return KillSwitchResult(allowed=allowed, method_discounts=discounts,
                            overall_multiplier=round(overall, 4), switches=switches,
                            evidence=evidence)


# ---------------- 置信度 ----------------
def method_confidence(
    name: str,
    *,
    pe_n: int = 0,
    growth_conf: str | None = None,
    cash_proxy: bool = False,
) -> float:
    """方法级置信度：基础值 + 数据完整度调整（输入数据越完整越高）。"""
    c = BASE_CONFIDENCE.get(name, 0.6)
    if name in ("relative_median_pe", "peg"):
        c += 0.15 if pe_n >= 8 else 0.08 if pe_n >= 3 else -0.10
    if name in ("relative_median_pe", "peg") and pe_n and pe_n < NEW_STOCK_PE_MIN:
        c -= 0.15  # 2.3：次新股 PE 样本不足 → 相对估值置信度降级
    if name == "dcf" and cash_proxy:
        c += 0.05
    if name in ("dcf", "peg") and growth_conf == "low":
        c -= 0.10
    if name == "ddm":
        c += 0.05
    return round(min(1.0, max(0.1, c)), 2)


def _valuation_confidence(
    confidences: list[float], weights: list[float],
    agreement: float, coverage: float,
) -> float:
    """综合置信度 = 加权方法置信度 × (覆盖度) × (一致性奖励)。"""
    if not confidences:
        return 0.0
    total_w = sum(weights)
    base = sum(c * w for c, w in zip(confidences, weights)) / total_w if total_w else 0.0
    conf = base * (0.55 + 0.45 * coverage) * (0.8 + 0.2 * max(0.0, min(1.0, agreement)))
    return round(min(1.0, conf), 3)


# ---------------- 结果 ----------------
@dataclass
class ValuationResult:
    business_type: str
    methods: dict[str, MethodResult]
    intrinsic: dict
    coverage_score: float
    evidence: list[str]
    params: dict = field(default_factory=dict)
    valuation_confidence: float = 0.0
    quality_multiplier: float | None = None
    risk_multiplier: float | None = None
    total_multiplier: float | None = None
    quality_tier: str | None = None
    quality_score: float | None = None
    kill_switches: list[str] = field(default_factory=list)
    method_agreement: float | None = None
    weights: dict = field(default_factory=dict)
    method_confidences: dict[str, float] = field(default_factory=dict)


def run_valuation(
    *,
    eps: float | None,
    bvps: float | None,
    pe_history: list[float],
    dividend: float | None,
    business_type: str = DEFAULT_TYPE,
    params: dict | None = None,
    # —— 数据库 financials 表已有字段（AkShare/存储均归一化）——
    ocfps: float | None = None,
    ocf_to_np: float | None = None,
    debt_to_assets: float | None = None,
    # —— 上游模块复用信号（M2/M3/M5/M6）——
    quality: dict | None = None,              # {"m2": 0-100, "m3": .., "m5": .., "m6": ..}
    m2_signals: list[str] | None = None,      # M2 风险信号 code 列表
    m3_cyclicality_flag: bool | None = None,
    m3_prosperity_code: str | None = None,    # up | flat | down
    m5_width: str | None = None,              # wide | medium | narrow | none
    m6_score: float | None = None,
    weights: dict | None = None,              # 方法权重覆盖（默认 METHOD_WEIGHTS + TYPE_WEIGHTS）
    confidence_delta: float = 0.0,            # LLM 行业校准的置信度增量（±0.1 内）
    # —— 周期股正常化保护输入（DB financials / valuation_history 表字段）——
    eps_history: list[float] | None = None,   # 年度 EPS 序列（正常化 EPS 用，正数）
    pb_history: list[float] | None = None,    # PB 历史（pb_band 用，正数）
    roe: float | None = None,                 # 最新年报 ROE（pb_roe 用，银行）
    ncav_ps: float | None = None,             # 1.1：每股净流动资产（NCAV 用）
    financial_subtype: str | None = None,     # 金融细类：bank | broker | insurance | other
) -> ValuationResult:
    """主入口：按业务类型路由方法 → kill_switch 裁剪 → 执行 → 质量乘数 → 加权汇总。"""
    p = {**default_params(), **(params or {})}
    routing = load_routing()
    allowed = routing.get(business_type, routing.get(DEFAULT_TYPE, DEFAULT_ROUTING[DEFAULT_TYPE]))

    # 亏损/微利（当期 EPS ≤ 0）：盈利类方法全部不适用，只用资产锚（PB），避免整块估值空白
    loss_mode = eps is not None and eps <= 0
    if loss_mode:
        allowed = ["pb_band"]

    # 金融细类路由：银行 PB-ROE / 券商正常化+PB / 保险相对PE+DDM
    if business_type == "financial" and financial_subtype in FINANCIAL_SUBTYPE_ROUTES:
        allowed = FINANCIAL_SUBTYPE_ROUTES[financial_subtype]

    g, r, tg, rf = p["growth_rate"], p["discount_rate"], p["terminal_growth"], p["risk_free_rate"]
    type_key = (
        f"financial_{financial_subtype}"
        if business_type == "financial" and financial_subtype in ("bank", "broker")
        else business_type
    )
    w = {**METHOD_WEIGHTS, **TYPE_WEIGHTS.get(type_key, {}), **(weights or {})}

    # 1) kill switch：先裁方法，再定折扣
    ks = kill_switch_check(
        allowed,
        m2_signals=m2_signals, debt_latest=debt_to_assets,
        m3_cyclicality_flag=m3_cyclicality_flag, m3_prosperity_code=m3_prosperity_code,
        m5_width=m5_width, m6_score=m6_score,
    )
    allowed = ks.allowed

    # 2) DCF 现金化利润代理（DB financials 的 ocf_to_np / ocfps 字段）
    cash_eps = cash_earnings_proxy(eps, ocf_to_np, ocfps)
    cash_proxy_used = cash_eps is not None and (ocf_to_np is not None or ocfps is not None)

    # 2b) 正常化 EPS：近 N 年 EPS 中位数（稳健，抗单年异常），供 relative_median_pe 正常化。
    #     适用：周期股 + 券商（金融外壳、周期内核，盈利随市场大幅波动）
    #     2.5：非周期股「近 1 年 EPS 显著低于多年中位（<50%）」的微利股同样启用正常化保护
    need_normalized = business_type == "cyclical" or (
        business_type == "financial" and financial_subtype in NORMALIZED_SUBTYPES
    )
    if not need_normalized and eps is not None and eps_history and len(eps_history) >= 5:
        hist_pos = [e for e in eps_history if e is not None and e > 0]
        if len(hist_pos) >= 5 and eps < 0.5 * statistics.median(hist_pos):
            need_normalized = True
    normalized_eps: float | None = None
    if need_normalized and eps_history:
        recent = [e for e in eps_history if e is not None and e > 0][-CYCLICAL_EPS_YEARS:]
        if recent:
            normalized_eps = round(statistics.median(recent), 4)
    micro_protect = (
        need_normalized
        and business_type not in ("cyclical",)
        and not (business_type == "financial" and financial_subtype in NORMALIZED_SUBTYPES)
    )

    # 3) 执行方法
    methods: dict[str, MethodResult] = {}
    if "dcf" in allowed:
        methods["dcf"] = dcf(eps, g, r, tg, cash_eps=cash_eps if cash_proxy_used else None)
    if "dcf_three_stage" in allowed:
        methods["dcf_three_stage"] = dcf_three_stage(
            eps, g, r, tg, cash_eps=cash_eps if cash_proxy_used else None
        )
    if "tang" in allowed:
        methods["tang"] = tang(eps, g, rf, pe_cap=TANG_PE_CAP.get(business_type))
    if "graham_number" in allowed:
        methods["graham_number"] = graham_number(eps, bvps)
    if "nav" in allowed:
        methods["nav"] = nav(bvps)
    if "ncav" in allowed:
        methods["ncav"] = ncav(ncav_ps)
    if "graham_formula" in allowed:
        # 2.6：格雷厄姆公式仅当期 PE < 10 时启用（1970s 参数过时，仅深度价值辅助）
        current_pe = pe_history[-1] if pe_history else None
        if current_pe is not None and current_pe >= GRAHAM_FORMULA_MAX_PE:
            methods["graham_formula"] = MethodResult(
                "graham_formula", None,
                note=f"当期 PE {current_pe:.1f} ≥ {GRAHAM_FORMULA_MAX_PE:.0f}，格雷厄姆公式（4.4/Y 过时参数）跳过",
            )
        else:
            methods["graham_formula"] = graham_formula(eps, g, rf)
    if "ddm" in allowed:
        # 2.4：传 EPS 供 DDM 校验分红覆盖率（分红率 >100% → 可持续性存疑）
        methods["ddm"] = ddm(dividend, g, r, eps=eps)
    if "relative_median_pe" in allowed:
        # 周期股/券商：正常化 EPS + PE 封顶（无 EPS 历史时至少对当期 EPS 封顶，避免 101 倍失真）
        methods["relative_median_pe"] = relative_median_pe(
            eps, pe_history,
            normalized_eps=normalized_eps,
            pe_cap=(CYCLICAL_PE_CAP if need_normalized else None),
        )
    if "pb_band" in allowed:
        methods["pb_band"] = pb_band(bvps, pb_history)
    if "pb_roe" in allowed:
        methods["pb_roe"] = pb_roe(bvps, roe, g, r)
    if "peg" in allowed:
        methods["peg"] = peg(eps, g, pe_history)

    # 4) kill_switch 方法级折扣（如 OCF_NP_DIVERGENCE → DCF ×0.85）
    for name, mult in ks.method_discounts.items():
        m = methods.get(name)
        if m is None or m.value is None:
            continue
        methods[name] = MethodResult(
            name,
            round(m.value * mult, 2),
            round(m.low * mult, 2) if m.low is not None else None,
            round(m.high * mult, 2) if m.high is not None else None,
            {**m.params, "kill_discount": mult},
            m.note,
        )

    # 5) 质量乘数 + kill 整体折扣（分开输出：质量乘数纯质量分，risk 乘数纯风险折扣）
    q_mult, q_tier, q_score, q_evidence = quality_multiplier(quality)
    final_mult = q_mult * ks.overall_multiplier

    evidence = [f"生意类型：{business_type}；适用方法：{', '.join(allowed)}；参数：{p}"]
    if micro_protect:
        evidence.append(
            "⚠️ 微利保护（2.5）：当期 EPS 显著低于多年中位，relative_median_pe 改用正常化 EPS"
        )
    if pe_history and len(pe_history) < NEW_STOCK_PE_MIN:
        evidence.append(
            f"⚠️ 次新股门槛（2.3）：PE 历史仅 {len(pe_history)} 交易日 < {NEW_STOCK_PE_MIN}，"
            f"相对估值参考性降低"
        )
    if eps_history and len([e for e in eps_history if e is not None]) < NEW_STOCK_ANNUAL_MIN:
        evidence.append(
            f"⚠️ 次新股门槛（2.3）：年报仅 {len([e for e in eps_history if e is not None])} 期 < {NEW_STOCK_ANNUAL_MIN}，"
            f"增速与正常化口径参考性降低"
        )
    if "need_normalized_micro" in locals() or need_normalized and business_type not in ("cyclical",):
        pass  # 微利正常化提示由下方统一输出
    if loss_mode:
        evidence.append("⚠️ 当期 EPS ≤ 0（亏损/微利）：盈利类方法不适用，仅用 PB 资产估值")
    if business_type == "financial" and financial_subtype:
        evidence.append(f"金融细类：{financial_subtype}（{', '.join(allowed)}）")
    for m in methods.values():
        if m.value is not None:
            note = f"（{m.note}）" if m.note else ""
            evidence.append(f"{m.name}: {m.value} 元{note}（{m.params}）")
        else:
            evidence.append(f"{m.name}: 跳过（{m.note}）")
    if cash_proxy_used and "dcf" in allowed:
        evidence.append(f"DCF 盈利基数：现金化利润代理 {cash_eps}（ocf_to_np×EPS 或 OCFPS）")
    evidence += ks.evidence
    evidence += q_evidence

    # 只认正值估值：0 不是估值而是缺数（如 bvps=0 时 pb_band 曾产出 0.0），
    # 混进加权中位数会把 mid/low 压成 0（603049 除零事故的源头）
    values = [(name, m.value) for name, m in methods.items() if m.value is not None and m.value > 0]
    # v2.3：区分「当前估值」与「未来估值」——未来口径（如唐朝法 3 年后）不进入
    # 当前内在价值区间，只作参考展示（避免把三年后价格误当今天的价值）。
    present = [(name, m.value) for name, m in methods.items()
               if m.value is not None and m.value > 0 and m.horizon_years is None]
    future = [(name, m) for name, m in methods.items()
              if m.value is not None and m.value > 0 and m.horizon_years is not None]
    if future and present:
        evidence.append(
            "未来估值（非现值）不进入当前内在价值区间："
            + "；".join(f"{name}={m.value:.2f}（{m.horizon_years}年后）" for name, m in future)
        )
    if not values:
        intrinsic = {"low": None, "high": None, "mid": None, "std": None, "method_agreement": None}
        score, conf, agreement = 0.0, 0.0, 0.0
        method_confidences = {}
    else:
        agg = present or values  # 极端兜底：无现值方法时退化为全部（含未来值）
        names = [n for n, _ in agg]
        vals = [v for _, v in agg]
        wlist = [w[n] for n in names]
        mid = _weighted_median(vals, wlist)
        wmean = _weighted_mean(vals, wlist)
        wstd = _weighted_std(vals, wlist, wmean)
        agreement = max(0.0, 1.0 - (wstd / mid)) if mid > 0 else 0.0
        raw_min, raw_max = min(vals), max(vals)
        band_low = mid - wstd
        if band_low <= 0:
            # 方法分歧过大（加权离散度 ≥ 中值）时 ±std 带下穿 0：下沿退化为最保守方法值，
            # 杜绝 low=0（此前 000831/600519 都输出 low=0，导致 M8 直接 OUT_OF_RANGE 放弃）
            band_low = raw_min
            evidence.append(
                "⚠️ 方法分歧过大（加权离散度 ≥ 中值）：下沿退化为最保守方法值 "
                f"{raw_min:.2f}，避免 0 值污染安全边际"
            )
        intrinsic = {
            "low": round(band_low * final_mult, 2),
            "mid": round(mid * final_mult, 2),
            "high": round((mid + wstd) * final_mult, 2),
            "std": round(wstd * final_mult, 2),
            "method_agreement": round(agreement, 3),
        }
        score = round(len(values) / len(allowed) * 100, 1) if allowed else 0.0
        if raw_min > 0 and raw_max / raw_min > 3:  # 方法间分歧过大，降低可估性评分
            score = max(0.0, score - 10)
            evidence.append(f"⚠️ 方法间分歧过大（极差 {raw_min:.0f}~{raw_max:.0f}），可估性降分")
        # 综合置信度：现值池；方法级置信度覆盖全部适用方法（含未来口径，供展示）
        all_names = [n for n, _ in values]
        all_confs = {
            n: method_confidence(
                n,
                pe_n=len(pe_history),
                growth_conf=p.get("growth_confidence"),
                cash_proxy=(cash_proxy_used and n == "dcf"),
            )
            for n in all_names
        }
        method_confidences = dict(all_confs)
        conf = _valuation_confidence(
            [all_confs[n] for n in names], wlist,
            agreement, len(values) / len(allowed) if allowed else 0.0,
        )
        conf = round(min(1.0, max(0.0, conf + confidence_delta)), 3)
        evidence.append(
            f"加权汇总（现值口径）：中位 {intrinsic['mid']} 元，离散度 ±{intrinsic['std']}（一致性 {agreement:.2f}），"
            f"乘数 {final_mult} → 区间 {intrinsic['low']} ~ {intrinsic['high']} 元"
        )
        evidence.append(f"估值置信度：{conf}（方法 {len(values)}/{len(allowed)}，一致性 {agreement:.2f}）")

    return ValuationResult(
        business_type=business_type,
        methods=methods,
        intrinsic=intrinsic,
        coverage_score=score,
        evidence=evidence,
        params=p,
        valuation_confidence=conf,
        quality_multiplier=round(q_mult, 4),
        risk_multiplier=round(ks.overall_multiplier, 4),
        total_multiplier=round(final_mult, 4),
        quality_tier=q_tier,
        quality_score=q_score,
        kill_switches=ks.switches,
        method_agreement=round(agreement, 3) if agreement else None,
        weights={k: v for k, v in w.items() if k in {n for n, _ in values}} or w,
        method_confidences=method_confidences,
    )
