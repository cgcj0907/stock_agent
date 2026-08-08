"""M2 财务质量引擎：纯函数、确定性、可测试。

输入：financials 表记录（period, roe, grossprofit_margin, netprofit_margin,
      debt_to_assets, ocfps, eps, ocf_to_np）
输出：0-100 评分 + 指标 + 风险信号 + 证据链（docs/01-design.md §3.2）

backlog 12.1（2026-08-07）：M2 分行业口径，同 M4 按 M1 生意类型/金融细类路由。
- config/financial_routing.yaml 是唯一事实来源，代码 FinancialProfile 为兜底；
- 金融/保险/银行：现金流比仅用年报（避免季度季节性误触发）、阈值放宽/中性，
  负债率 90%+ 属行业常态不再按"杠杆过高"扣分 → 不再因 OCF/NP<0.8 误判一票否决。
"""
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from value_agent.core.contracts import RiskSignal

logger = logging.getLogger(__name__)

# 权重（合计 100）
W_PROFIT = 30   # 盈利能力
W_STABLE = 20   # 稳定性
W_CASH = 20     # 现金流质量
W_HEALTH = 15   # 财务健康
W_RISK = 15     # 风险信号

# ---- 分行业口径（backlog 12.1）----
_PROFILE_FIELDS = (
    "cashflow_mode", "cashflow_annual_only", "cashflow_threshold",
    "leverage_mode", "ocf_divergence_severity",
)


@dataclass(frozen=True)
class FinancialProfile:
    """M2 财务质量评估口径。

    cashflow_mode: standard（通用 0.8 硬阈值）| lenient（金融口径，仅年报+阈值放宽）
                   | skip（现金流口径不适用，按中性计）
    cashflow_annual_only: 现金流比是否只用年报（季度 OCF/NP 季节波动大，易误触发）
    cashflow_threshold: 触发 OCF_NP_DIVERGENCE 的阈值
    leverage_mode: standard | industry（金融/保险高杠杆视为行业常态，不扣分）
    ocf_divergence_severity: OCF_NP_DIVERGENCE 信号严重度（standard=medium / 金融=low）
    """
    cashflow_mode: str = "standard"
    cashflow_annual_only: bool = False
    cashflow_threshold: float = 0.8
    leverage_mode: str = "standard"
    ocf_divergence_severity: str = "medium"


DEFAULT_PROFILE = FinancialProfile()

_PROFILE_LABELS: dict[str, str] = {
    "cashflow_mode": {
        "standard": "现金流按通用口径",
        "lenient": "现金流按金融口径（仅年报、阈值放宽）",
        "skip": "现金流口径不适用（按中性计）",
    },
    "leverage_mode": {
        "standard": "杠杆按通用分档",
        "industry": "高杠杆视为金融行业常态",
    },
}


def _profile_label(profile: FinancialProfile) -> str:
    """行业口径的一句话说明（进 evidence，供 LLM/用户理解为什么没用通用规则）。"""
    parts = [
        _PROFILE_LABELS["cashflow_mode"].get(profile.cashflow_mode, profile.cashflow_mode),
        _PROFILE_LABELS["leverage_mode"].get(profile.leverage_mode, profile.leverage_mode),
    ]
    return "；".join(parts)


def _routing_candidates() -> tuple[Path, ...]:
    return (
        Path("config/financial_routing.yaml"),
        Path(__file__).resolve().parents[3] / "config" / "financial_routing.yaml",
    )


def _load_financial_routing() -> dict[str, dict]:
    """读 config/financial_routing.yaml（12.1 唯一事实来源），缺失/解析失败回退空（代码兜底）。"""
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    for path in _routing_candidates():
        if not path.exists():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            out: dict[str, dict] = {}
            for key, meta in (raw.get("routing") or {}).items():
                prof = {k: v for k, v in (meta or {}).items() if k in _PROFILE_FIELDS and v is not None}
                out[key] = prof
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("financial_routing.yaml 解析失败：%s", type(exc).__name__)
            continue
    return {}


def resolve_profile(
    business_type: str | None = None,
    financial_subtype: str | None = None,
) -> FinancialProfile:
    """按 M1 生意类型/金融细类解析财务质量口径（12.1）。

    优先级：financial_subtype 配置 > business_type 配置 > default > 代码默认。
    """
    routing = _load_financial_routing()
    merged = {k: getattr(DEFAULT_PROFILE, k) for k in _PROFILE_FIELDS}
    for key in ("default", business_type, financial_subtype):
        if key and key in routing:
            merged.update(routing[key])
    return FinancialProfile(**merged)


@dataclass
class FinancialQualityResult:
    score: float
    metrics: dict
    signals: list[RiskSignal]  # 结构化风险信号（code/severity/metric/message/evidence）
    evidence: list[str]
    details: dict = field(default_factory=dict)
    profile: FinancialProfile = field(default_factory=lambda: DEFAULT_PROFILE)


def annual_records(records: list[dict]) -> list[dict]:
    """只保留年报（period 以 1231 结尾）的记录；无年报则回退全部。

    季度 ROE/毛利率是单季或累计口径，与年报不可比，做水平判断时应优先年报。
    """
    annual = [r for r in records if str(r.get("period", "")).endswith("1231")]
    return annual or list(records)


def latest_annual(records: list[dict], key: str):
    """最新年报（1231）中某字段的值；无年报则取最新一期。"""
    pool = sorted(annual_records(records), key=lambda r: str(r.get("period", "")), reverse=True)
    return pool[0].get(key) if pool else None


def analyze_financial_quality(
    records: list[dict],
    *,
    business_type: str | None = None,
    financial_subtype: str | None = None,
) -> FinancialQualityResult:
    """主入口：输入财报记录列表，输出评分与证据。

    business_type / financial_subtype 来自 M1（backlog 12.1）：金融/保险/银行按行业口径
    评估现金流与杠杆；缺失时走通用口径（向后兼容旧调用与 quick 流）。
    """
    profile = resolve_profile(business_type, financial_subtype)
    recs = sorted(
        (r for r in records if r.get("period")), key=lambda r: r["period"], reverse=True
    )
    n = len(recs)
    evidence = [
        f"数据：{n} 期财报（{recs[-1]['period']} ~ {recs[0]['period']}）" if n else "数据：无财报记录"
    ]
    if profile != DEFAULT_PROFILE:
        evidence.append(f"口径：{_profile_label(profile)}（按 M1 生意类型 {business_type or '?'}/{financial_subtype or '?'}）")

    annual = annual_records(recs)
    # 现金流比口径：金融行业只用年报（12.1，季度 OCF/NP 季节波动大易误触发）
    cash_pool = annual if profile.cashflow_annual_only else recs

    def col(name: str, pool=None) -> list[float]:
        return [
            r[name]
            for r in (pool or recs)
            if r.get(name) is not None and math.isfinite(r[name])
        ]

    roe = col("roe", annual)          # 年度 ROE（避免季度口径失真）
    np = col("netprofit_margin", annual)
    debt = col("debt_to_assets", annual)
    ocf_to_np = col("ocf_to_np", cash_pool)
    ocfps = col("ocfps", cash_pool)
    eps = col("eps", cash_pool)

    score_profit, p_notes, p_metrics = _profitability(roe, np, debt)
    score_stable, s_notes = _stability(roe)
    score_cash, c_notes, c_metrics = _cashflow(ocf_to_np, ocfps, eps, profile, business_type)
    score_health, h_notes, h_metrics = _health(debt, profile)
    score_risk, signals = _risks(recs, roe, debt, ocf_to_np, ocfps, eps, profile)

    total = round(
        score_profit + score_stable + score_cash + score_health + score_risk, 1
    )
    total = max(0.0, min(100.0, total))

    metrics = {
        "years": len(annual) if annual else n,
        **p_metrics,
        **c_metrics,
        **h_metrics,
    }
    details = {
        "盈利": p_notes,
        "稳定": s_notes,
        "现金流": c_notes,
        "杠杆": h_notes,
        "信号": [sig.message for sig in signals],
    }
    evidence += p_notes + s_notes + c_notes + h_notes
    for sig in signals:
        evidence.append(f"⚠️ 信号：{sig.message}")

    return FinancialQualityResult(
        score=total, metrics=metrics, signals=signals, evidence=evidence,
        details=details, profile=profile,
    )


# ---- 子评分 ----
def _profitability(roe: list[float], np: list[float], debt: list[float]):
    """盈利能力 30 分：ROE 水平 + 杜邦拆解 + 趋势。"""
    notes: list[str] = []
    if not roe:
        return W_PROFIT / 2, ["⚠️ 缺少 ROE 数据，盈利能力按中性计"], {"roe_latest": None}

    latest, mean = roe[0], statistics.mean(roe)
    if latest >= 15:
        score = W_PROFIT
    elif latest >= 10:
        score = 24
    elif latest >= 5:
        score = 16
    elif latest >= 0:
        score = 8
    else:
        score = 0

    note = f"ROE 最新 {latest:.1f}%，{len(roe)} 期均值 {mean:.1f}%"
    if len(roe) >= 3 and mean < latest - 5:
        score -= 3
        note += "（均值显著低于最新值，注意盈利下滑）"
    elif len(roe) >= 3 and mean > latest + 5:
        score += 2
        note += "（均值高于最新值，当前盈利偏弱）"
    notes.append(note)

    # 杜邦拆解（隐含周转率 = ROE / (净利率 × 权益乘数)）
    dupont: dict = {}
    if np and debt:
        em = 1.0 / (1.0 - debt[0]) if debt[0] < 1 else None
        if em:
            turnover = (mean / 100.0) / (np[0] / 100.0 * em) if np[0] else None
            dupont = {
                "net_margin": round(np[0], 2),
                "equity_multiplier": round(em, 2),
                "implied_asset_turnover": round(turnover, 2) if turnover else None,
            }
            notes.append(
                f"杜邦：净利率 {np[0]:.1f}% × 隐含周转 {dupont['implied_asset_turnover']} × 杠杆 {em:.2f}"
            )
    return score, notes, {"roe_latest": latest, "roe_mean": round(mean, 2), **dupont}


def _stability(roe: list[float]):
    """稳定性 20 分：ROE 波动率 + 是否亏损年。"""
    if len(roe) < 3:
        return W_STABLE / 2, ["⚠️ ROE 期数不足 3 期，稳定性按中性计"]
    mean = statistics.mean(roe)
    std = statistics.stdev(roe)
    cv = std / abs(mean) if mean else 1.0
    has_loss = any(r < 0 for r in roe)
    if cv <= 0.15 and not has_loss:
        score, note = W_STABLE, f"ROE 波动小（CV={cv:.2f}，无亏损年）"
    elif cv <= 0.3 and not has_loss:
        score, note = 14, f"ROE 波动中等（CV={cv:.2f}，无亏损年）"
    elif has_loss:
        score, note = 6, f"存在亏损年份（ROE<0），CV={cv:.2f}"
    else:
        score, note = 8, f"ROE 波动较大（CV={cv:.2f}）"
    return score, [note]


def _cashflow_label(business_type: str | None, profile: FinancialProfile) -> str:
    """现金流口径标签（v2.2：不再对所有 lenient 行业写死'金融口径'）。"""
    if profile.leverage_mode == "industry":
        return "金融"
    return {
        "cyclical": "周期",
        "growth": "成长",
        "financial": "金融",
        "bank": "金融",
        "broker": "金融",
        "insurance": "金融",
    }.get(business_type, "行业")


def _cashflow(
    ocf_to_np: list[float], ocfps: list[float], eps: list[float],
    profile: FinancialProfile, business_type: str | None = None,
):
    """现金流质量 20 分。

    standard：经营现金流/净利润 ≥1 为优、<0.8 预警（通用行业）。
    lenient / skip（金融/银行/保险等）：净利润主要由投资端决定、经营现金流被存款进出/
    保费/赔付/准备金变动主导，OCF/NP 低不构成盈利质量差的证据——lenient 仅年报+阈值放宽，
    skip（银行）按中性计。
    """
    notes: list[str] = []
    mode = profile.cashflow_mode
    label = _cashflow_label(business_type, profile)
    if mode == "skip":
        return (
            W_CASH / 2,
            ["⚠️ 金融行业经营现金流/净利不适用于盈利质量判断（银行被存款进出主导、保险净利润主要由投资端决定），按中性计；建议改用营运利润/拨备/不良率/内含价值/NBV 等专业口径"],
            {"ocf_to_np_min": None},
        )
    if ocf_to_np:
        ratio = min(ocf_to_np)
        good = sum(1 for v in ocf_to_np if v >= 1.0)
        if mode == "lenient":
            if ratio >= 0.8:
                score, note = W_CASH, f"经营现金流/净利润 最低 {ratio:.2f}（{label}口径，{good}/{len(ocf_to_np)} 期达标）"
            elif ratio >= profile.cashflow_threshold:
                score, note = 16, f"经营现金流/净利润 最低 {ratio:.2f}（{label}口径偏低但在容忍线内）"
            elif ratio >= 0.3:
                score, note = 12, f"⚠️ 经营现金流/净利润 最低 {ratio:.2f}（{label}口径偏低，需结合营运利润/内含价值验证）"
            else:
                score, note = 8, f"⚠️ 经营现金流/净利润 最低 {ratio:.2f}（{label}口径显著偏低，盈利含金量存疑）"
        else:
            if ratio >= 1.0:
                score, note = W_CASH, f"经营现金流/净利润 ≥1（{good}/{len(ocf_to_np)} 期）"
            elif ratio >= 0.8:
                score, note = 14, f"经营现金流/净利润 最低 {ratio:.2f}（{good}/{len(ocf_to_np)} 期达标）"
            else:
                score, note = 6, f"⚠️ 经营现金流/净利润 最低 {ratio:.2f}，盈利含金量存疑"
        notes.append(note)
        return score, notes, {"ocf_to_np_min": round(ratio, 2)}
    if ocfps and eps:
        ratio = min(v / e for v, e in zip(ocfps, eps) if e)
        if mode == "lenient":
            score = W_CASH if ratio >= 0.8 else (
                16 if ratio >= profile.cashflow_threshold else (12 if ratio >= 0.3 else 8)
            )
        else:
            score = W_CASH if ratio >= 1.0 else (14 if ratio >= 0.8 else 6)
        notes.append(f"每股经营现金流/每股收益 最低 {ratio:.2f}（由于源数据缺失现金流净额，采用每股数据估算）")
        return score, notes, {"ocfps_eps_min": round(ratio, 2)}
    return W_CASH / 2, ["⚠️ 缺少现金流数据，按中性计"], {"ocf_to_np_min": None}


def _health(debt: list[float], profile: FinancialProfile):
    """财务健康 15 分：资产负债率水平与趋势。

    industry 模式（金融/保险/银行）：负债率 90%+ 是吸收存款/保单准备金等经营性负债的
    行业常态，高杠杆不构成风险扣分；仅异常值（<1% 或 >150%）按数据坏值处理。
    """
    if not debt:
        return W_HEALTH / 2, ["⚠️ 缺少资产负债率数据，按中性计"], {"debt_to_assets": None}
    latest = debt[0]
    # 数据防御：负债率不可能 <1% 或 >150%（疑似数据源坏值），按中性计并警告，
    # 避免把坏数据当成「低杠杆优秀」抬高分（如个别周期异常值）
    if not (0.01 <= latest <= 1.5):
        return (
            W_HEALTH / 2,
            [f"⚠️ 资产负债率 {latest:.4f} 超出合理区间（疑似数据异常），按中性计"],
            {"debt_to_assets": None},
        )
    if profile.leverage_mode == "industry" and 0.5 <= latest <= 1.5:
        score, note = 11, f"资产负债率 {latest:.1%}（金融/保险行业高杠杆属常态，按中性偏高分）"
    elif latest <= 0.4:
        score, note = W_HEALTH, f"资产负债率 {latest:.1%}，财务稳健"
    elif latest <= 0.6:
        score, note = 11, f"资产负债率 {latest:.1%}，杠杆中等"
    elif latest <= 0.8:
        score, note = 6, f"资产负债率 {latest:.1%}，杠杆偏高"
    else:
        score, note = 2, f"⚠️ 资产负债率 {latest:.1%}，杠杆过高"
    if len(debt) >= 2 and debt[0] - debt[-1] > 0.1:
        score = max(0, score - 3)
        note += "（较早期明显上升）"
    return score, [note], {"debt_to_assets_latest": round(latest, 3)}


def _risks(recs, roe, debt, ocf_to_np, ocfps, eps, profile: FinancialProfile):
    """风险信号 15 分：命中信号扣分，并输出结构化信号清单（RiskSignal）。

    signals 供 M9 风险聚合 / M11 监控直接消费，见 docs/09-module-contracts.md §4.2。
    """
    signals: list[RiskSignal] = []
    mode = profile.cashflow_mode
    if mode != "skip" and ocf_to_np and min(ocf_to_np) < profile.cashflow_threshold:
        signals.append(RiskSignal(
            code="OCF_NP_DIVERGENCE", severity=profile.ocf_divergence_severity,
            metric="ocf_to_np_min",
            message=f"经营现金流与净利润背离（最低 <{profile.cashflow_threshold}）",
            evidence=f"ocf_to_np 最低 {min(ocf_to_np):.2f}",
        ))
    if mode != "skip" and ocf_to_np is None and not (ocfps and eps):
        signals.append(RiskSignal(
            code="CASHFLOW_MISSING", severity="medium", metric="ocf_to_np",
            message="缺少现金流数据，无法验证盈利含金量",
        ))
    if len(roe) >= 2 and abs(roe[0] - roe[1]) > 10:
        signals.append(RiskSignal(
            code="ROE_SPIKE", severity="medium", metric="roe",
            message=f"ROE 单年突变（{roe[0]:.1f}% → {roe[1]:.1f}%），需核查",
        ))
    if roe and roe[0] > 40:
        signals.append(RiskSignal(
            code="ROE_HIGH", severity="medium", metric="roe",
            message=f"ROE 异常偏高（{roe[0]:.1f}%），需核查是否含一次性收益",
        ))
    if len(debt) >= 2 and debt[0] - debt[-1] > 0.1:
        signals.append(RiskSignal(
            code="DEBT_RISING", severity="medium", metric="debt_to_assets",
            message=f"资产负债率近一年上升超 10pct（{debt[-1]:.1%} → {debt[0]:.1%}）",
        ))
    if roe and any(r < 0 for r in roe):
        signals.append(RiskSignal(
            code="LOSS_YEAR", severity="high", metric="roe",
            message="存在亏损年份（ROE<0）",
        ))
    score = max(0.0, W_RISK - 5.0 * len(signals))
    return score, signals
