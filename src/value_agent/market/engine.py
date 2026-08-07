"""M7 价格与情绪引擎：估值历史分位 + 股债性价比（格雷厄姆"市场先生"）。"""
from __future__ import annotations

from dataclasses import dataclass, field

MIN_SAMPLES = 10  # 分位计算最小样本数（不足则判"样本不足"）


@dataclass
class MarketResult:
    pe_percentile: float | None
    pb_percentile: float | None
    position: str        # 极低估/低估/合理/高估/泡沫/样本不足
    score: float
    evidence: list[str] = field(default_factory=list)


def _percentile(value: float, history: list[float]) -> float:
    """当前值在历史序列中的分位（≤当前值的占比，0~1）。"""
    if not history:
        return 0.0
    return sum(1.0 for v in history if v <= value) / len(history)


def assess_market(valuation_history: dict, risk_free: float = 0.04) -> MarketResult:
    recs = sorted(
        (r for r in valuation_history.get("records", []) if r.get("trade_date")),
        key=lambda r: r["trade_date"], reverse=True,
    )
    pe_hist = [r["pe_ttm"] for r in recs if r.get("pe_ttm")]
    pb_hist = [r["pb"] for r in recs if r.get("pb")]
    latest_pe = pe_hist[0] if pe_hist else None
    latest_pb = pb_hist[0] if pb_hist else None
    latest_dv = next((r["dv_ttm"] for r in recs if r.get("dv_ttm")), None)

    evidence = [f"估值历史样本：PE {len(pe_hist)} 期 / PB {len(pb_hist)} 期"]

    pe_ok = len(pe_hist) >= MIN_SAMPLES and latest_pe is not None
    pb_ok = len(pb_hist) >= MIN_SAMPLES and latest_pb is not None

    if not pe_ok and not pb_ok:
        return MarketResult(
            pe_percentile=None, pb_percentile=None, position="样本不足（<10 期）",
            score=50.0,
            evidence=evidence + ["⚠️ 历史样本不足，分位与价格位置暂不可靠"],
        )

    pe_pct = _percentile(latest_pe, pe_hist) if pe_ok else None
    pb_pct = _percentile(latest_pb, pb_hist) if pb_ok else None
    if not pe_ok:
        # 银行/保险/资产型公司：PE 常失真或缺失，PB 更有效 → 不因缺 PE 误判"样本不足"
        evidence.append("⚠️ PE 历史样本不足，以 PB 分位判定价格位置（银行/资产型公司常见）")
    max_pct = max(p for p in (pe_pct, pb_pct) if p is not None)

    if max_pct < 0.2:
        position, score = "极低估", 95.0
    elif max_pct < 0.4:
        position, score = "低估", 80.0
    elif max_pct < 0.6:
        position, score = "合理", 60.0
    elif max_pct < 0.8:
        position, score = "高估", 30.0
    else:
        position, score = "泡沫", 10.0

    ey = (1 / latest_pe if latest_pe and latest_pe > 0 else None) if pe_ok else None
    pct_parts = []
    if pe_pct is not None:
        pct_parts.append(f"PE(TTM) {latest_pe} 分位 {pe_pct:.0%}")
    if pb_pct is not None:
        pct_parts.append(f"PB {latest_pb} 分位 {pb_pct:.0%}")
    evidence += [
        "；".join(pct_parts),
        f"股债性价比：盈利收益率 {ey:.1%} vs 无风险利率 {risk_free:.1%}（{position}）" if ey else "盈利收益率不可计算（PE 样本不足）",
    ]
    if latest_dv is not None:
        evidence.append(f"股息率 {latest_dv:.1%} vs 无风险利率 {risk_free:.1%}（{'有吸引力' if latest_dv >= risk_free else '不占优'}）")
    evidence.append(f"价格位置：{position}（市场先生报价）")
    return MarketResult(
        pe_percentile=round(pe_pct, 4) if pe_pct is not None else None,
        pb_percentile=round(pb_pct, 4) if pb_pct is not None else None,
        position=position, score=score, evidence=evidence,
    )
