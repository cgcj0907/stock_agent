"""M2 财务质量引擎：纯函数、确定性、可测试。

输入：financials 表记录（period, roe, grossprofit_margin, netprofit_margin,
      debt_to_assets, ocfps, eps, ocf_to_np）
输出：0-100 评分 + 指标 + 风险信号 + 证据链（docs/01-design.md §3.2）
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

# 权重（合计 100）
W_PROFIT = 30   # 盈利能力
W_STABLE = 20   # 稳定性
W_CASH = 20     # 现金流质量
W_HEALTH = 15   # 财务健康
W_RISK = 15     # 风险信号


@dataclass
class FinancialQualityResult:
    score: float
    metrics: dict
    signals: list[str]
    evidence: list[str]
    details: dict = field(default_factory=dict)


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


def analyze_financial_quality(records: list[dict]) -> FinancialQualityResult:
    """主入口：输入财报记录列表，输出评分与证据。"""
    recs = sorted(
        (r for r in records if r.get("period")), key=lambda r: r["period"], reverse=True
    )
    n = len(recs)
    evidence = [
        f"数据：{n} 期财报（{recs[-1]['period']} ~ {recs[0]['period']}）" if n else "数据：无财报记录"
    ]

    annual = annual_records(recs)

    def col(name: str, pool=None) -> list[float]:
        return [
            r[name]
            for r in (pool or recs)
            if r.get(name) is not None and math.isfinite(r[name])
        ]

    roe = col("roe", annual)          # 年度 ROE（避免季度口径失真）
    gp = col("grossprofit_margin", annual)
    np = col("netprofit_margin", annual)
    debt = col("debt_to_assets", annual)
    ocf_to_np = col("ocf_to_np")
    ocfps = col("ocfps")
    eps = col("eps")

    score_profit, p_notes, p_metrics = _profitability(roe, np, debt)
    score_stable, s_notes = _stability(roe)
    score_cash, c_notes, c_metrics = _cashflow(ocf_to_np, ocfps, eps)
    score_health, h_notes, h_metrics = _health(debt)
    score_risk, signals = _risks(recs, roe, debt, ocf_to_np, ocfps, eps)

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
        "信号": signals,
    }
    evidence += p_notes + s_notes + c_notes + h_notes
    for sig in signals:
        evidence.append(f"⚠️ 信号：{sig}")

    return FinancialQualityResult(
        score=total, metrics=metrics, signals=signals, evidence=evidence, details=details
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
    """稳定性 20 分：ROE 波动率 + 亏损年份。"""
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


def _cashflow(ocf_to_np: list[float], ocfps: list[float], eps: list[float]):
    """现金流质量 20 分：经营现金流/净利润 ≥1（连续 5 年）。"""
    notes: list[str] = []
    if ocf_to_np:
        ratio = min(ocf_to_np)
        good = sum(1 for v in ocf_to_np if v >= 1.0)
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
        score = W_CASH if ratio >= 1.0 else (14 if ratio >= 0.8 else 6)
        notes.append(f"每股经营现金流/每股收益 最低 {ratio:.2f}（无直接 ocf_to_np，用 ocfps/eps）")
        return score, notes, {"ocfps_eps_min": round(ratio, 2)}
    return W_CASH / 2, ["⚠️ 缺少现金流数据，按中性计"], {"ocf_to_np_min": None}


def _health(debt: list[float]):
    """财务健康 15 分：资产负债率水平与趋势。"""
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
    if latest <= 0.4:
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


def _risks(recs, roe, debt, ocf_to_np, ocfps, eps):
    """风险信号 15 分：命中信号扣分，并输出信号清单。"""
    signals: list[str] = []
    if ocf_to_np and min(ocf_to_np) < 0.8:
        signals.append("经营现金流与净利润背离（最低 <0.8）")
    if ocf_to_np is None and not (ocfps and eps):
        signals.append("缺少现金流数据，无法验证盈利含金量")
    if len(roe) >= 2 and abs(roe[0] - roe[1]) > 10:
        signals.append(f"ROE 单年突变（{roe[0]:.1f}% → {roe[1]:.1f}%），需核查")
    if roe and roe[0] > 40:
        signals.append(f"ROE 异常偏高（{roe[0]:.1f}%），需核查是否含一次性收益")
    if len(debt) >= 2 and debt[0] - debt[-1] > 0.1:
        signals.append(f"资产负债率近一年上升超 10pct（{debt[-1]:.1%} → {debt[0]:.1%}）")
    if roe and any(r < 0 for r in roe):
        signals.append("存在亏损年份（ROE<0）")
    score = max(0.0, W_RISK - 5.0 * len(signals))
    return score, signals
