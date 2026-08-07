"""M5 护城河引擎：规则层 = 「财务代理评级」，不冒充最终护城河结论。

两层制（docs/09-module-contracts.md §4 M5）：
- 规则层只产出「财务代理评级」：相对行业基准的 ROE/利润率/杠杆 相对评分、
  五类来源中可计算的两类代理（无形资产/成本规模）、以及侵蚀趋势信号；
- 最终护城河宽度由 agent 层合成（rule_proxy × LLM 定性），本模块保持
  纯函数、确定性、可测试（不读配置、不联网）。

注意：
- PEER_BENCHMARKS 是静态行业基准表（不同生意类型的「行业中位数」代理），
  接上真实同行中位数数据源后可整体替换；当前用它解决「绝对阈值偏爱高毛利行业、
  低估银行/公用事业」的问题。
- 周期行业（cyclical）用「跨周期均值 ROE」参与相对评分（去周期位置），
  ROE 波动/下滑对周期股是行业属性而非护城河被侵蚀，记入 cycle_notes 而不进
  erosion_signals（避免污染 M9 的侵蚀风险）。
- debt_to_assets 含合同负债（客户预收），对订单型/预收型行业高负债率
  ≠ 高杠杆风险，以 debt_note 明示，不做机械扣分误伤。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from value_agent.business_model.engine import classify_business_type
from value_agent.financials.quality import annual_records

# 静态行业基准（行业中位数代理）：roe/margin/debt 为「同行中位」的代理值。
# margin_key 区分毛利率（消费品/周期/成长）与净利率（金融：毛利率口径不适用）；
# debt_median=None 表示该维度不适用（金融杠杆天然高，不做相对扣分）。
PEER_BENCHMARKS: dict[str, dict] = {
    "consumer_monopoly": {
        "label": "消费垄断", "roe_median": 18.0,
        "margin_key": "grossprofit_margin", "margin_median": 45.0, "debt_median": 0.40,
    },
    "growth": {
        "label": "成长", "roe_median": 12.0,
        "margin_key": "grossprofit_margin", "margin_median": 30.0, "debt_median": 0.45,
    },
    "cyclical": {
        "label": "周期", "roe_median": 8.0,
        "margin_key": "grossprofit_margin", "margin_median": 20.0, "debt_median": 0.55,
    },
    "financial": {
        "label": "金融", "roe_median": 10.0,
        "margin_key": "netprofit_margin", "margin_median": 30.0, "debt_median": None,
    },
    "asset_based": {
        "label": "资产型", "roe_median": 6.0,
        "margin_key": "grossprofit_margin", "margin_median": 25.0, "debt_median": 0.50,
    },
    "stable_dividend": {
        "label": "高分红稳定", "roe_median": 12.0,
        "margin_key": "grossprofit_margin", "margin_median": 30.0, "debt_median": 0.40,
    },
    "generic": {
        "label": "一般", "roe_median": 10.0,
        "margin_key": "grossprofit_margin", "margin_median": 25.0, "debt_median": 0.50,
    },
}

# 代理档位（财务代理评级，非最终护城河结论）
_TIER_BANDS = ((70.0, "宽"), (50.0, "中"), (30.0, "窄"))

# 5.6：周期行业跨周期均值窗口（固定近 8 年，避免年份数随数据变长而漂移）
CYCLE_WINDOW_YEARS = 8

# 订单型/预收型行业的杠杆口径提示（debt_to_assets 含合同负债）
_DEBT_NOTE = (
    "debt_to_assets 含合同负债（客户预收），订单型/预收型行业高负债率"
    "可能反映订单饱满而非高杠杆风险"
)


@dataclass
class SourceSignal:
    """五类护城河来源中，规则层可计算的代理信号。"""

    source: str      # 无形资产 / 成本/规模优势（转换成本/网络效应待 LLM 定性）
    basis: str       # 依据说明
    strength: str    # strong / medium


@dataclass
class PeerContext:
    """同行对比上下文：公司值 vs 行业基准（中位代理）。"""

    benchmark: str            # 生意类型键
    label: str                # 基准展示名
    roe_company: float | None
    roe_median: float
    margin_key: str | None
    margin_company: float | None
    margin_median: float | None
    debt_company: float | None
    debt_median: float | None
    debt_note: str | None = None  # 杠杆口径说明（debt_to_assets 含合同负债）


@dataclass
class MoatResult:
    rule_tier: str            # 宽 / 中 / 窄 / 无（财务代理档位）
    score: float              # 0-100 代理评分
    signals: list[str]
    sources: list[SourceSignal] = field(default_factory=list)
    peer: PeerContext | None = None
    erosion_signals: list[str] = field(default_factory=list)  # 结构侵蚀信号（喂 M9）
    cycle_notes: list[str] = field(default_factory=list)      # 周期属性备注（不喂 M9）
    evidence: list[str] = field(default_factory=list)


def _erosion_signals(
    roe: list[float], gm: list[float], debt: list[float], *, cyclical: bool = False
) -> tuple[list[str], list[str]]:
    """侵蚀趋势信号：ROE 下滑 / 利润率压缩 / 杠杆抬升 / 盈利波动大。

    返回 (erosion_signals, cycle_notes)：
    - 周期行业里 ROE 相关信号（下滑、波动大）是行业属性（周期位置/波动），
      记入 cycle_notes 而不进 erosion_signals，避免把周期性误报成护城河被侵蚀。
    - 利润率压缩 / 杠杆抬升对周期行业仍视为结构侵蚀信号。
    """
    out: list[str] = []
    cycle_notes: list[str] = []
    if len(roe) >= 2:
        mean = statistics.mean(roe)
        if roe[0] < mean - 5:
            msg = f"ROE 下滑：最新 {roe[0]:.1f}% vs {len(roe)} 期均值 {mean:.1f}%"
            if cyclical:
                cycle_notes.append(msg)
            else:
                out.append(msg)
    if len(gm) >= 3:
        mean = statistics.mean(gm)
        if gm[0] < mean - 5:
            out.append(f"利润率压缩：最新 {gm[0]:.1f}% vs {len(gm)} 期均值 {mean:.1f}%")
    if len(debt) >= 2:
        mean = statistics.mean(debt)
        if debt[0] > mean + 0.1:
            out.append(f"杠杆抬升：最新 {debt[0]:.2f} vs {len(debt)} 期均值 {mean:.2f}")
    if len(roe) >= 3:
        mean = statistics.mean(roe)
        cv = statistics.stdev(roe) / abs(mean) if mean else 0.0
        if cv > 0.5:
            msg = f"盈利波动大（ROE 变异系数 {cv:.2f}）"
            if cyclical:
                cycle_notes.append(msg)
            else:
                out.append(msg)
    return out, cycle_notes


def _identify_sources(
    roe: list[float], gm: list[float], debt: list[float], bench: dict, margin_key: str,
    rd_ratio: list[float] | None = None,
) -> list[SourceSignal]:
    """五类来源中可计算的代理：高利润率→无形资产/定价权；低杠杆+稳 ROE→成本/规模；
    5.4：研发费用率 ≥5% → 技术壁垒代理（无形资产来源增强）。"""
    sources: list[SourceSignal] = []
    margin_median = bench.get("margin_median")
    if margin_key and margin_median is not None and gm:
        diff = gm[0] - margin_median
        if diff >= 5:
            sources.append(SourceSignal(
                source="无形资产",
                basis=(
                    f"{margin_key} {gm[0]:.1f}% ≥ 行业基准 {margin_median:.1f}%"
                    f"（+{diff:.1f}pct，定价权/品牌代理）"
                ),
                strength="strong" if diff >= 15 else "medium",
            ))
    debt_median = bench.get("debt_median")
    if debt_median is not None and debt and roe:
        ratio = debt[0] / debt_median
        if ratio <= 0.9 and roe[0] >= bench["roe_median"] - 3:
            sources.append(SourceSignal(
                source="成本/规模优势",
                basis=(
                    f"杠杆 {debt[0]:.2f} 低于行业基准 {debt_median:.2f}（比值 {ratio:.2f}）"
                    f"且 ROE {roe[0]:.1f}% 不弱于同行"
                ),
                strength="strong" if ratio <= 0.6 else "medium",
            ))
    # 5.4：研发强度 ≥5% → 技术壁垒代理（专利/研发驱动的无形资产来源）
    if rd_ratio and rd_ratio[0] >= 0.05:
        sources.append(SourceSignal(
            source="无形资产",
            basis=f"研发费用率 {rd_ratio[0]:.1%} ≥ 5%（技术壁垒/研发投入代理）",
            strength="strong" if rd_ratio[0] >= 0.10 else "medium",
        ))
    return sources


def assess_moat(
    financials: dict,
    *,
    industry: str = "",
    business_type: str | None = None,
    peer_benchmarks: dict | None = None,
) -> MoatResult:
    """规则层护城河评估：相对行业基准的财务代理评级（非最终护城河结论）。

    输入财务记录（period/roe/grossprofit_margin/netprofit_margin/debt_to_assets）
    与可选行业/生意类型；输出代理档位、信号、来源代理、同行上下文、侵蚀信号与周期备注。
    """
    recs = [r for r in financials.get("records", []) if r.get("period")]
    annual = sorted(annual_records(recs), key=lambda r: r["period"], reverse=True)
    roe = [r["roe"] for r in annual if r.get("roe") is not None]
    gm = [r["grossprofit_margin"] for r in annual if r.get("grossprofit_margin") is not None]
    np = [r["netprofit_margin"] for r in annual if r.get("netprofit_margin") is not None]
    # 5.2：有息负债率优先（不含合同负债，杠杆信号更真实）；debt_to_assets 兜底
    debt = [
        (r["interest_debt_ratio"] if r.get("interest_debt_ratio") is not None else r["debt_to_assets"])
        for r in annual if r.get("interest_debt_ratio") is not None or r.get("debt_to_assets") is not None
    ]
    rd_ratio = [r["rd_ratio"] for r in annual if r.get("rd_ratio") is not None]
    contract_ratio = [r["contract_liability_ratio"] for r in annual if r.get("contract_liability_ratio") is not None]

    if not recs:
        return MoatResult("无", 0.0, [], [], None, [], [], ["无财务数据"])

    benchmarks = dict(PEER_BENCHMARKS)
    if peer_benchmarks:
        benchmarks.update(peer_benchmarks)

    roe_latest = roe[0] if roe else None
    gm_latest = gm[0] if gm else None
    debt_latest = debt[0] if debt else None

    bt = business_type or classify_business_type(
        industry or "", roe_latest, gm_latest, debt_latest
    )
    if bt not in benchmarks:
        bt = "generic"
    bench = benchmarks[bt]
    is_cyclical = bt == "cyclical"
    margin_key = bench.get("margin_key") or "grossprofit_margin"
    margin_pool = np if margin_key == "netprofit_margin" else gm
    margin_latest = margin_pool[0] if margin_pool else None

    # 5.6/5.7：周期行业用「近 8 年跨周期均值」参与相对评分（去周期位置）——
    # ROE / 利润率 / 杠杆 都取跨周期均值，避免低谷期当期值误伤
    roe_compare = roe_latest
    margin_compare = margin_latest
    debt_compare = debt_latest
    if is_cyclical and len(annual) >= 3:
        window = annual[:CYCLE_WINDOW_YEARS]
        w_roe = [r["roe"] for r in window if r.get("roe") is not None]
        w_margin = [r[margin_key] for r in window if r.get(margin_key) is not None] if margin_key else []
        w_debt = [r["debt_to_assets"] for r in window if r.get("debt_to_assets") is not None]
        if w_roe:
            roe_compare = statistics.mean(w_roe)
        if w_margin:
            margin_compare = statistics.mean(w_margin)
        if w_debt:
            debt_compare = statistics.mean(w_debt)

    score, signals = 0.0, []
    dims_present, dims_applicable = 0, 0

    # 1) ROE 相对同行（周期用跨周期均值）
    if roe_compare is not None:
        dims_applicable += 1
        dims_present += 1
        diff = roe_compare - bench["roe_median"]
        if diff >= 8:
            score += 35
        elif diff >= 3:
            score += 28
        elif diff >= -3:
            score += 18
        elif diff >= -8:
            score += 8
        if is_cyclical and roe_compare != roe_latest:
            signals.append(
                f"ROE（跨周期均值 {roe_compare:.1f}%，最新 {roe_latest:.1f}%）"
                f"vs {bench['label']}行业中位 {bench['roe_median']:.0f}%"
                f"（{'+' if diff >= 0 else ''}{diff:.1f}pct）"
            )
        else:
            signals.append(
                f"ROE {roe_compare:.1f}% vs {bench['label']}行业中位 {bench['roe_median']:.0f}%"
                f"（{'+' if diff >= 0 else ''}{diff:.1f}pct）"
            )
        if len(roe) >= 3 and diff >= 0:  # 稳定性加成只给「不弱于同行中位」的公司
            mean = statistics.mean(roe)
            cv = statistics.stdev(roe) / abs(mean) if mean else 0.0
            if cv <= 0.15:
                score += 10
                signals.append("ROE 稳定（变异系数 ≤0.15）")
            elif cv <= 0.30:
                score += 5
                signals.append("ROE 波动可控")

    # 2) 利润率相对同行（金融用净利率口径）
    if margin_compare is not None and bench.get("margin_median") is not None:
        dims_applicable += 1
        dims_present += 1
        diff = margin_compare - bench["margin_median"]
        if diff >= 15:
            score += 30
        elif diff >= 5:
            score += 22
        elif diff >= -5:
            score += 12
        margin_display = (
            f"利润率（跨周期均值 {margin_compare:.1f}%，最新 {margin_latest:.1f}%）"
            if is_cyclical and margin_compare != margin_latest
            else f"利润率 {margin_compare:.1f}%"
        )
        signals.append(
            f"{margin_display} vs {bench['label']}行业中位 {bench['margin_median']:.0f}%"
            f"（{'+' if diff >= 0 else ''}{diff:.1f}pct）"
        )

    # 3) 杠杆相对同行（金融等杠杆天然高的维度跳过）
    if debt_compare is not None and bench.get("debt_median") is not None:
        dims_applicable += 1
        dims_present += 1
        ratio = debt_compare / bench["debt_median"]
        if ratio <= 0.6:
            score += 15
        elif ratio <= 0.9:
            score += 10
        elif ratio <= 1.1:
            score += 5
        debt_display = (
            f"杠杆（跨周期均值 {debt_compare:.2f}，最新 {debt_latest:.2f}）"
            if is_cyclical and debt_compare != debt_latest
            else f"杠杆 {debt_compare:.2f}"
        )
        signals.append(
            f"{debt_display} vs {bench['label']}行业中位 {bench['debt_median']:.2f}"
            f"（比值 {ratio:.2f}）"
        )

    # 4) 数据完整度（维度缺失时按占比折减，避免「一个 ROE 撑满全分」）
    if dims_applicable:
        score += 10 * dims_present / dims_applicable

    # 5) 侵蚀/趋势扣分（上限 15）；周期行业的 ROE 波动/下滑进 cycle_notes 不扣分
    erosion, cycle_notes = _erosion_signals(roe, gm, debt, cyclical=is_cyclical)
    score -= min(15.0, 8.0 * len(erosion))

    score = max(0.0, min(100.0, score))
    tier = next((label for thr, label in _TIER_BANDS if score >= thr), "无")

    debt_note = None
    if debt_compare is not None and bench.get("debt_median") is not None:
        # 5.2：合同负债占比高 → 明确提示「报表负债率被客户预收抬高，有息口径更真实」
        if contract_ratio and contract_ratio[0] >= 0.15:
            debt_note = (
                f"合同负债占比 {contract_ratio[0]:.0%}，报表负债率含客户预收；"
                "已用有息负债率参与杠杆对比（订单型行业高负债≠高杠杆风险）"
            )
        else:
            debt_note = _DEBT_NOTE
    peer = PeerContext(
        benchmark=bt, label=bench["label"],
        roe_company=roe_compare, roe_median=bench["roe_median"],
        margin_key=margin_key, margin_company=margin_latest,
        margin_median=bench.get("margin_median"),
        debt_company=debt_latest, debt_median=bench.get("debt_median"),
        debt_note=debt_note,
    )
    sources = _identify_sources(roe, gm, debt, bench, margin_key, rd_ratio=rd_ratio or None)

    evidence = [
        f"规则层=财务代理评级：{tier}（{score:.0f}/100），基准={bench['label']}（{bt}）",
        f"信号：{signals if signals else '无明显优势信号'}",
    ]
    if is_cyclical and (roe_compare != roe_latest or margin_compare != margin_latest or debt_compare != debt_latest):
        evidence.append(
            "周期行业：ROE/利润率/杠杆用近 8 年跨周期均值参与相对评分（去周期位置）"
        )
    if bench.get("margin_median") is None or bench.get("debt_median") is None:
        skipped = [k for k, v in (("利润率", bench.get("margin_median")), ("杠杆", bench.get("debt_median"))) if v is None]
        evidence.append(f"注：{bench['label']}基准下「{'/'.join(skipped)}」维度不适用，代理评分上限受限")
    if debt_note:
        evidence.append(f"注：{debt_note}")
    # 数据缺失兜底：维度缺失时按中性处理并明示「档位可能低估」，避免把缺数据误读成真实结论
    if margin_compare is None and bench.get("margin_median") is not None:
        evidence.append("⚠️ 利润率数据缺失，该维度按中性处理，代理档位可能低估实际护城河")
    if debt_compare is None and bench.get("debt_median") is not None:
        evidence.append("⚠️ 杠杆数据缺失，该维度按中性处理，代理档位可能低估实际护城河")
    if erosion:
        evidence.append(f"⚠️ 规则层侵蚀信号：{'；'.join(erosion)}")
    if cycle_notes:
        evidence.append(f"周期属性备注：{'；'.join(cycle_notes)}")
    evidence.append(
        "⚠️ 此为相对行业基准的财务代理评级，非最终护城河结论；"
        "品牌/网络效应/转换成本等定性来源由 LLM 层补充"
    )
    return MoatResult(
        rule_tier=tier, score=round(score, 1), signals=signals,
        sources=sources, peer=peer, erosion_signals=erosion,
        cycle_notes=cycle_notes, evidence=evidence,
    )
