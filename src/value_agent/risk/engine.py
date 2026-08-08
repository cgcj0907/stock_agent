"""M9 风险与否决引擎：聚合各模块风险信号 + 一票否决（确定性规则）。

Risk Registry（docs/09-module-contracts.md §4 M9）：risk_items 为结构化对象，
供 M10（vetoes/handoff.veto_flags）/ M11（monitor_candidates、severity）直接消费，
不再字符串转义。

一票否决（docs/01-design.md §3.9）：审计非标 / 造假信号命中 / 质押率 > 80% /
行业明确下行 + 高杠杆；M2 财务质量极差（<30）为硬否决底线。

backlog 2026-08-07 落地：
- 7.15  M9 消费 M7 sentiment_heat：高估/泡沫 + 情绪过热 → 升级 severity；低估 + 过热 → 接飞刀项。
- 8.3   risk_items 输出 expected_loss = P×L（概率×损失幅度），按期望损失排序；
        M9 分数改按期望损失口径（严重度权重 × 期望损失因子）。
- 8.5   压力情景接入 M4 intrinsic_range + current_price → 绝对回撤金额 + 建议仓位上限。
- 8.8   风险项按 (source_module, trigger) 去重，保留最高 severity。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.sessions.models import ModuleResult

# 严重度排序 / 加权（1 条 critical 的扣分 ≈ 1 条 medium 的 4 倍，进 M9 分数）
SEVERITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEVERITY_WEIGHT: dict[str, float] = {"critical": 40.0, "high": 25.0, "medium": 10.0, "low": 4.0}

# M2 造假红旗信号：≥2 个同时命中 → 一票否决（单个红旗只是核查信号，不构成否决）
FRAUD_FLAG_CODES: frozenset[str] = frozenset({"OCF_NP_DIVERGENCE", "ROE_HIGH", "ROE_SPIKE"})
# M6 治理风险码 → 一票否决（审计非标意见）
VETO_RISK_CODES: frozenset[str] = frozenset({"AUDIT_QUALIFIED"})
# 质押率 > 80% → 否决（设计阈值）
PLEDGE_VETO_RATIO = 0.8
# 行业明确下行 + 高杠杆组合否决的杠杆阈值（资产负债率 ≥ 60%，与 M2 杠杆偏高 0.6~0.8 档对齐）
LEVERAGE_VETO_THRESHOLD = 0.6

# 8.3：每类风险的（发生概率, 损失幅度）系数 —— expected_loss = P×L（可回测校准）
RISK_PROFILE: dict[str, tuple[float, float]] = {
    "财务": (0.20, 0.50),
    "景气": (0.30, 0.40),
    "护城河": (0.25, 0.40),
    "治理": (0.10, 0.60),
    "估值情绪": (0.30, 0.30),
    "安全边际": (0.20, 0.40),
    "接飞刀": (0.25, 0.35),  # 低估 + 情绪过热：追跌买入的短期回撤风险
}

# 情绪热度阈值（与 M7 一致）
SENTIMENT_HOT = 0.66


@dataclass
class RiskResult:
    risk_items: list[dict]  # [{id, category, severity, source_module, trigger, impact, mitigation, veto_candidate, expected_loss}]
    vetoes: list[dict]  # 一票否决对象 [{id, reason, severity}]
    veto: list[str]  # 兼容：否决 reason 字符串列表（M10 继续消费）
    monitor_candidates: list[str]  # 需长期监控的风险项 id（M11 直接转规则）
    score: float
    max_loss_scenario: dict = field(default_factory=dict)  # 压力测试：景气腰斩 + 估值腰斩
    veto_flags: list[str] = field(default_factory=list)  # handoff.veto_flags（M10 用）
    max_severity: str = "low"  # handoff.max_severity
    evidence: list[str] = field(default_factory=list)


def _expected_loss(category: str) -> float:
    prob, loss = RISK_PROFILE.get(category, (0.2, 0.4))
    return round(prob * loss, 4)


def _risk_item(
    seq: int,
    category: str,
    severity: str,
    source_module: str,
    trigger: str,
    impact: str,
    mitigation: str = "",
    veto_candidate: bool = False,
) -> dict:
    return {
        "id": f"R-{seq:03d}",
        "category": category,
        "severity": severity,
        "source_module": source_module,
        "trigger": trigger,
        "impact": impact,
        "mitigation": mitigation,
        "veto_candidate": veto_candidate,
        "expected_loss": _expected_loss(category),  # 8.3：P×L 期望损失
    }


def _max_loss_scenario(high_items: list[dict], m8: dict, m4: dict | None = None) -> dict:
    """压力测试：景气腰斩（盈利 -50%）+ 估值腰斩（倍数 -50%），内在价值下沿同步下调。

    estimated_downside_pct：现价相对「腰斩后内在价值下沿」的理论最大回撤。
    设 M8 折扣率 d = 1 - 现价/内在价值下沿，则现价 = V(1-d)，腰斩后 V' = V/4，
    回撤 = 1 - V' / 现价 = 1 - 1 / (4(1-d))。d 缺失时仅定性。
    8.5：接入 M4 intrinsic_range + current_price → 绝对回撤金额 + 建议仓位上限。
    """
    drivers = [it["impact"] for it in high_items]
    estimated = None
    discount = m8.get("discount")
    if discount is not None:
        try:
            denom = 4.0 * (1.0 - float(discount))
            if denom > 0:
                estimated = round((1.0 - 1.0 / denom) * 100, 1)
        except (TypeError, ValueError, ZeroDivisionError):
            estimated = None

    scenario: dict = {
        "scenario": "压力测试：景气腰斩 + 估值腰斩",
        "assumptions": "盈利水平腰斩（-50%）且估值倍数腰斩（-50%），内在价值下沿同步下调",
        "estimated_downside_pct": estimated,
        "note": "基于 M8 安全边际折扣率估算" if estimated is not None else "缺少安全边际折扣数据，仅定性评估",
        "drivers": drivers or [],
    }
    # 8.5：绝对回撤金额 + 建议仓位上限（基于 M4 现价与内在价值下沿）
    price = None
    if m4:
        price = m4.get("current_price")
    if estimated is not None and price is not None:
        try:
            price = float(price)
            downside_amount = round(price * estimated / 100.0, 2)
            cap = max(0.0, min(0.25, 0.25 * (1.0 - estimated / 100.0)))
            scenario.update({
                "current_price": price,
                "intrinsic_low": m4.get("intrinsic_value", {}).get("low") if m4 else None,
                "estimated_downside_amount": downside_amount,
                "suggested_position_cap": round(cap, 4),
            })
        except (TypeError, ValueError):
            pass
    return scenario


def _dedupe_items(items: list[dict]) -> list[dict]:
    """8.8：按 (source_module, trigger, impact) 去重，保留最高 severity（同 severity 保留先出现）。

    只合并「同源同触发同描述」的真实重复项（如 M2 信号被多处上报）；
    不同描述的同 trigger（如两条不同内容的侵蚀风险）不合并。
    """
    seen: dict[tuple[str, str, str], dict] = {}
    order: list[tuple[str, str, str]] = []
    for it in items:
        key = (it.get("source_module", ""), it.get("trigger", ""), it.get("impact", ""))
        if key in seen:
            cur = seen[key]
            if SEVERITY_ORDER.get(it["severity"], 3) < SEVERITY_ORDER.get(cur["severity"], 3):
                seen[key] = it
        else:
            seen[key] = it
            order.append(key)
    return [seen[k] for k in order]


def assess_risk(inputs: dict[str, ModuleResult], assumptions: dict | None = None) -> RiskResult:
    """聚合 M2/M3/M4/M5/M6/M7/M8 输出，生成结构化风险清单与一票否决。"""
    assumptions = assumptions or {}
    items: list[dict] = []
    vetoes: list[dict] = []
    n = 0

    def out(mid: str) -> dict:
        r = inputs.get(mid)
        return r.outputs if r else {}

    def veto(reason: str) -> None:
        vetoes.append({"id": f"V-{len(vetoes) + 1:03d}", "reason": reason, "severity": "critical"})

    # M2 财务风险（分数契约：handoff.quality_score；降级/旧输出回退 ModuleResult.score，
    # 不再读不存在的 outputs["score"]——旧实现导致 M2<30 否决在生产恒不触发）
    m2_res = inputs.get("M2_financial_quality")
    m2 = m2_res.outputs if m2_res else {}
    m2_handoff = m2.get("handoff") or {}
    m2_score = m2_handoff.get("quality_score")
    if m2_score is None:
        m2_score = m2_res.score if m2_res else None
    m2_signals = m2.get("signals") or []
    m2_codes = [s.get("code") for s in m2_signals if isinstance(s, dict) and s.get("code")]
    fraud_hits = [c for c in m2_codes if c in FRAUD_FLAG_CODES]
    if len(fraud_hits) >= 2:
        veto(f"造假信号命中（M2 多项红旗：{'/'.join(fraud_hits)}）")
    for sig in m2_signals:
        n += 1
        if isinstance(sig, dict):
            items.append(_risk_item(
                n, "财务", sig.get("severity", "medium"), "M2_financial_quality",
                sig.get("code") or sig.get("message", ""), sig.get("message", ""),
                mitigation="跟踪现金流/利润勾稽",
            ))
        else:
            items.append(_risk_item(n, "财务", "medium", "M2_financial_quality", sig, sig))
    if m2_score is not None:
        if m2_score < 30:
            veto("财务质量极差（M2<30）")
        elif m2_score < 60:
            n += 1
            items.append(_risk_item(n, "财务", "medium", "M2_financial_quality",
                                    "financial_quality_below_60", "财务质量一般"))

    # M3 景气风险（契约：读 handoff.prosperity_code，不再直接读中文 prosperity）
    m3 = out("M3_growth")
    m3_handoff = m3.get("handoff") or {}
    if m3_handoff.get("prosperity_code") == "down":
        n += 1
        items.append(_risk_item(n, "景气", "medium", "M3_growth", "prosperity_code=down",
                                "行业景气下行", mitigation="财报季重点复查景气指标"))

    # M5 护城河风险（宽度 + 侵蚀风险 + 持久性）
    m5 = out("M5_moat")
    if m5.get("width") in ("无", "窄"):
        n += 1
        impact = "护城河无（竞争压力大）" if m5.get("width") == "无" else "护城河较窄（竞争压力大）"
        items.append(_risk_item(n, "护城河", "medium", "M5_moat", f"width={m5.get('width')}", impact))
    m5_handoff = m5.get("handoff") or {}
    durability = m5_handoff.get("moat_durability")
    trend = m5_handoff.get("moat_trend") or m5_handoff.get("trend")
    for er in m5_handoff.get("erosion_risks") or []:
        if not str(er).strip():
            continue
        n += 1
        # 5.13：侵蚀风险 severity 细化（读 M5 handoff 的 durability + trend）
        #   durability=low 且 trend=eroding → critical（接近一票否决的护城河风险）
        #   durability=low 或 trend=eroding → high（进 M11 监控候选）
        #   否则 → medium
        if durability == "low" and trend == "eroding":
            sev = "critical"
        elif durability == "low" or trend == "eroding":
            sev = "high"
        else:
            sev = "medium"
        items.append(_risk_item(
            n, "护城河", sev, "M5_moat", "erosion_risk",
            str(er), mitigation="跟踪护城河来源指标与竞争格局变化",
        ))

    # M6 治理风险：读 handoff 契约字段（governance_score）+ governance_risk_codes 结构化信号
    m6 = out("M6_governance")
    m6_handoff = m6.get("handoff") or {}
    g_score = m6_handoff.get("governance_score")
    if g_score is not None and g_score < 55:
        n += 1
        items.append(_risk_item(n, "治理", "medium", "M6_governance",
                                "governance_score<55", "治理/回报股东偏弱"))
    for gc in m6_handoff.get("governance_risk_codes") or []:
        if not isinstance(gc, dict) or not gc.get("code"):
            continue
        code = gc["code"]
        # 一票否决：审计非标意见
        if code in VETO_RISK_CODES:
            veto(f"审计非标（{gc.get('description') or code}）")
            continue
        # 一票否决：质押率 > 80%（规则层风险码带 ratio 字段；LLM 无 ratio 时不触发）
        if code == "SHARE_PLEDGE":
            ratio = gc.get("ratio")
            try:
                ratio = float(ratio) if ratio is not None else None
            except (TypeError, ValueError):
                ratio = None
            if ratio is not None and ratio > PLEDGE_VETO_RATIO:
                veto(f"质押率过高（{ratio:.0%} > 80%）")
                continue
        sev = gc.get("severity")
        sev = sev if sev in ("low", "medium", "high", "critical") else "medium"
        n += 1
        items.append(_risk_item(
            n, "治理", sev, "M6_governance",
            f"governance_risk_code={code}",
            gc.get("description") or code,
            mitigation="跟踪治理事件后续进展与信息披露",
            veto_candidate=bool(gc.get("veto_candidate")),  # 6.5：高危治理码 → 长期监控候选
        ))

    # M7 估值情绪风险（7.15：情绪过热升级；低估+过热 → 接飞刀）
    m7 = out("M7_market")
    heat = m7.get("sentiment_heat")
    if m7.get("position") in ("高估", "泡沫"):
        sev = "high" if m7.get("position") == "泡沫" else "medium"
        if heat is not None and heat >= SENTIMENT_HOT:
            sev = "critical" if m7.get("position") == "泡沫" else "high"
        n += 1
        impact = f"估值位置{m7['position']}（市场情绪过热）"
        if heat is not None and heat >= SENTIMENT_HOT:
            impact += f" + 情绪热度 {heat:.0%}"
        items.append(_risk_item(n, "估值情绪", sev, "M7_market",
                                f"position={m7.get('position')}", impact))
    if m7.get("position") in ("极低估", "低估") and heat is not None and heat >= SENTIMENT_HOT:
        n += 1
        items.append(_risk_item(
            n, "接飞刀", "medium", "M7_market",
            "position=cheap+sentiment_hot",
            f"低估但情绪过热（热度 {heat:.0%}）：追跌买入可能接飞刀",
            mitigation="等待情绪降温/分档建仓，不一次性买入",
        ))

    # M8 安全边际风险
    m8 = out("M8_safety_margin")
    if m8.get("discount") is not None and m8["discount"] < 0:
        n += 1
        items.append(_risk_item(n, "安全边际", "high", "M8_safety_margin",
                                "discount<0", "安全边际为负（现价高于内在价值下沿）"))

    # 一票否决：行业明确下行 + 高杠杆（潜在永久损失路径：景气反转时高杠杆放大亏损）
    m2_metrics = m2.get("metrics") or {}
    debt = m2_metrics.get("debt_to_assets_latest")
    if (
        m3_handoff.get("prosperity_code") == "down"
        and debt is not None
        and debt >= LEVERAGE_VETO_THRESHOLD
    ):
        veto(f"行业景气明确下行 + 高杠杆（M3 prosperity=down 且 M2 资产负债率 {debt:.0%} ≥ 60%）")

    # 显式否决（测试/用户覆盖）
    for reason in assumptions.get("veto_reasons") or []:
        veto(str(reason))

    # 8.8：去重（同 source_module + trigger 只留最高 severity）
    items = _dedupe_items(items)
    # 8.3：按期望损失排序（期望损失降序 → severity 降序），替代纯严重度排序
    items.sort(key=lambda it: (
        -it.get("expected_loss", 0.0),
        SEVERITY_ORDER.get(it["severity"], SEVERITY_ORDER["low"]),
    ))

    veto = [v["reason"] for v in vetoes]
    monitor_candidates = [
        it["id"] for it in items
        if it["severity"] in ("high", "critical") or it["veto_candidate"]
    ]

    # 8.3：分数改按期望损失口径——严重度权重 × 期望损失因子（0.5~1.5），否决每条 -30
    score = 100.0
    for it in items:
        base = SEVERITY_WEIGHT.get(it["severity"], 10.0)
        factor = min(1.5, max(0.5, 1.0 + it.get("expected_loss", 0.0) * 2.0))
        score -= base * factor
    score = max(0.0, score - 30.0 * len(vetoes))
    max_loss_scenario = _max_loss_scenario(
        [it for it in items if it["severity"] in ("high", "critical")], m8,
        m4=out("M4_valuation"),
    )
    veto_flags = [v["id"] for v in vetoes]
    max_severity = (
        "critical"
        if vetoes
        else max(items, key=lambda it: SEVERITY_ORDER.get(it["severity"], 3)).get("severity", "low")
        if items
        else "low"
    )
    evidence = [
        f"风险清单（{len(items)} 项，按期望损失排序）：{[it['impact'] for it in items] if items else '未发现明显风险'}"
    ]
    if veto:
        evidence.append(f"🚫 一票否决：{veto}")
    evidence.append(
        f"压力情景：{max_loss_scenario['scenario']}，"
        f"估算最大回撤 {max_loss_scenario['estimated_downside_pct']}%"
        if max_loss_scenario["estimated_downside_pct"] is not None
        else f"压力情景：{max_loss_scenario['scenario']}（{max_loss_scenario['note']}）"
    )
    evidence.append("⚠️ 治理事件风险经 M6 governance_risk_codes 上报；红队定性见 LLM 层")
    return RiskResult(
        risk_items=items, vetoes=vetoes, veto=veto,
        monitor_candidates=monitor_candidates,
        score=round(score, 1), max_loss_scenario=max_loss_scenario,
        veto_flags=veto_flags, max_severity=max_severity,
        evidence=evidence,
    )
