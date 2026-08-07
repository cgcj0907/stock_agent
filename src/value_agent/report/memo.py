"""投资备忘录生成：从会话结果组装 markdown 备忘录（docs/01-design.md §6）。"""
from __future__ import annotations

import json

from value_agent.sessions.models import ModuleStatus, Session


def build_memo(session: Session) -> str:
    """生成备忘录：M10 结论 + 关键模块输出 + 模块执行表 + 假设 + 免责声明。"""
    results = session.module_results
    title = session.company_name or session.company_code
    lines: list[str] = [
        f"# {title} 投资备忘录",
        "",
        f"- 日期：{session.created_at:%Y-%m-%d %H:%M} UTC",
        f"- 会话：`{session.id}`",
        f"- 工作流：`{session.workflow_id}`",
        f"- 数据快照：`{session.data_snapshot_id or '—'}`",
        f"- 模型版本：`{session.model_version}`",
        f"- 状态：`{session.status.value}`",
        "",
        "## 执行摘要",
    ]

    m10 = results.get("M10_decision")
    if m10 and m10.outputs.get("conclusion"):
        lines += [
            f"- **结论：{m10.outputs['conclusion']}**（总分 {m10.outputs['total']}，建议仓位 {m10.outputs['position']:.0%}）",
            f"- 五维评分：{_json(m10.outputs['dimensions'])}",
        ]
        m4 = results.get("M4_valuation")
        m8 = results.get("M8_safety_margin")
        if m4 and m4.outputs.get("intrinsic_value"):
            iv = m4.outputs["intrinsic_value"]
            conf = m4.outputs.get("valuation_confidence")
            q_mult = m4.outputs.get("quality_multiplier")
            lines.append(
                f"- 内在价值区间：{iv['low']} ~ {iv['high']} 元（中值 {iv['mid']}"
                f"{('，离散度 ±' + str(iv['std'])) if iv.get('std') is not None else ''}），"
                f"现价 {m4.outputs.get('current_price')} 元"
            )
            if conf is not None:
                lines.append(f"- 估值置信度：{conf}；方法一致性：{iv.get('method_agreement')}")
            if q_mult is not None:
                lines.append(
                    f"- 质量乘数：{q_mult}（档位 {m4.outputs.get('quality_tier')}，"
                    f"风险折扣 {m4.outputs.get('risk_multiplier')}，综合 {m4.outputs.get('total_multiplier')}）"
                )
            ks = m4.outputs.get("kill_switches") or []
            if ks:
                lines.append(f"- ⚠️ 触发风险开关：{'、'.join(ks)}")
        if m8 and m8.outputs.get("buy_price"):
            lines.append(
                f"- 安全边际：买入 ≤ {m8.outputs['buy_price']} 元 / 卖出 ≥ {m8.outputs['sell_price']} 元"
                f"（{m8.outputs['status']}）"
            )
        if m10.outputs.get("vetoed"):
            lines.append(f"- ⚠️ 否决项：{m10.outputs['vetoed']}")
        # 8.5：决策理由（qualitative.decision_reasons）+ handoff 展示
        qual = m10.outputs.get("qualitative") or {}
        reasons = qual.get("decision_reasons") or []
        if reasons:
            lines += ["", "### 决策理由（M10）", ""]
            for r_ in reasons:
                lines.append(f"- {r_}")
        handoff10 = m10.outputs.get("handoff") or {}
        if handoff10:
            lines += ["", "### 决策契约（M10 handoff）", ""]
            lines.append(f"- decision_code：`{handoff10.get('decision_code')}`；"
                         f"blocked_by_veto：`{handoff10.get('blocked_by_veto')}`；"
                         f"position：`{handoff10.get('position')}`")
    else:
        lines.append("- 结论：M10 未产出（评分卡未执行）")

    lines += ["", "## 模块执行结果", "", "| 模块 | 状态 | 评分 | 证据数 |", "|---|---|---|---|"]
    for agent_id in sorted(results):
        r = results[agent_id]
        lines.append(
            f"| {r.module} | {r.status.value} | "
            f"{r.score if r.score is not None else '—'} | {len(r.evidence)} |"
        )

    # M6 治理摘要（6.9：LLM 治理判断与风险码「只存不用」→ 进备忘录）
    m6 = results.get("M6_governance")
    if m6 and m6.outputs.get("handoff"):
        handoff6 = m6.outputs["handoff"]
        g_score = handoff6.get("governance_score")
        if g_score is not None:
            lines += [
                "",
                "## 治理与资本配置（M6）",
                "",
                (
                    f"- 治理评分：{g_score}（分红 {m6.outputs.get('dividend_years', 0)} 期，"
                    f"最新分红率 {m6.outputs.get('payout_latest')}）"
                ),
            ]
            codes = handoff6.get("governance_risk_codes") or []
            if codes:
                lines.append(f"- ⚠️ 治理风险码：{'；'.join(str(c.get('code')) for c in codes if isinstance(c, dict))}")
            cap_flag = handoff6.get("capital_allocation_flag")
            if cap_flag:
                lines.append(f"- 资本配置代理档位：{cap_flag}")
            qual6 = m6.outputs.get("llm_qualitative")
            if isinstance(qual6, dict):
                for key, label in (("shareholder_alignment", "股东利益一致性"),
                                   ("capital_allocation", "资本配置判断"),
                                   ("disclosure_quality", "信息披露质量"),
                                   ("conclusion", "LLM 结论")):
                    v = qual6.get(key)
                    if v:
                        lines.append(f"- {label}：{v}")

    # M2 财务质量要点
    m2 = results.get("M2_financial_quality")
    if m2 and m2.outputs.get("metrics"):
        metrics = m2.outputs["metrics"]
        lines += [
            "",
            "## 财务质量（M2）",
            "",
            f"- ROE：最新 {metrics.get('roe_latest')}%，均值 {metrics.get('roe_mean')}%",
            f"- 杜邦：净利率 {metrics.get('net_margin')}% × 隐含周转 {metrics.get('implied_asset_turnover')} × 杠杆 {metrics.get('equity_multiplier')}",
            f"- 现金流/净利润最低：{metrics.get('ocf_to_np_min')}；资产负债率：{metrics.get('debt_to_assets_latest')}",
        ]
        signals = m2.outputs.get("signals") or []
        if signals:
            msgs = [s.get("message") if isinstance(s, dict) else s for s in signals]
            lines.append(f"- ⚠️ 风险信号：{'；'.join(msgs)}")

    # M4 方法对照 + M8
    m4 = results.get("M4_valuation")
    m8 = results.get("M8_safety_margin")
    if m4 and m4.outputs.get("methods"):
        lines += ["", "## 估值与安全边际（M4/M8）", "", "| 方法 | 每股价值 |", "|---|---|"]
        for m in m4.outputs["methods"]:
            val = m.get("value")
            reason = m.get("reason") or m.get("note") or ""
            lines.append(f"| {m.get('method')} | {val if val is not None else '跳过（' + reason + '）'} |")
        if m8 and m8.outputs.get("buy_price"):
            lines.append(
                f"\n- 安全边际：现价 {m8.outputs.get('price')} 元，折扣率 {m8.outputs.get('discount')}，"
                f"要求折扣 {m8.outputs.get('required_discount')}，买入 ≤ {m8.outputs['buy_price']} 元，"
                f"卖出 ≥ {m8.outputs['sell_price']} 元"
            )
        llm_q = m4.outputs.get("llm_qualitative") if m4 else None
        if isinstance(llm_q, dict) and llm_q.get("calibration"):
            calib = llm_q["calibration"]
            parts = []
            if calib.get("business_type_override"):
                parts.append(f"路由→{calib['business_type_override']}")
            if calib.get("parameter_adjustments"):
                parts.append(f"参数 {calib['parameter_adjustments']}")
            if calib.get("method_weight_adjustments"):
                parts.append(f"权重 {calib['method_weight_adjustments']}")
            if calib.get("valuation_confidence_delta"):
                parts.append(f"置信度 {calib['valuation_confidence_delta']:+.2f}")
            if parts:
                lines.append(f"\n- LLM 行业校准：{'；'.join(parts)}")
            if calib.get("industry_notes"):
                lines.append(f"- 行业判断：{'；'.join(calib['industry_notes'])}")
            if calib.get("risk_notes"):
                lines.append(f"- 行业风险：{'；'.join(calib['risk_notes'])}")

    # M9 风险摘要（8.9：Top 风险 + 否决 + 压力情景 + 红队结论）
    m9 = results.get("M9_risk")
    if m9 and m9.outputs.get("risk_items") is not None:
        lines += ["", "## 风险与否决（M9）", ""]
        risk_items = m9.outputs.get("risk_items") or []
        if risk_items:
            lines.append(f"- Top 风险（{len(risk_items)} 项）：")
            for it in risk_items[:5]:
                if isinstance(it, dict):
                    lines.append(f"  - [{it.get('severity')}] {it.get('impact')}（触发 {it.get('trigger')}）")
        vetoes = m9.outputs.get("vetoes") or []
        if vetoes:
            lines.append(f"- 🚫 一票否决：{'；'.join(str(v.get('reason')) for v in vetoes if isinstance(v, dict))}")
        max_loss = m9.outputs.get("max_loss_scenario") or {}
        if max_loss.get("estimated_downside_pct") is not None:
            lines.append(f"- 压力情景：{max_loss.get('scenario')}，估算最大回撤 {max_loss.get('estimated_downside_pct')}%")
        red = m9.outputs.get("llm_red_team")
        if isinstance(red, dict):
            if red.get("key_assumptions"):
                lines.append(f"- 红队关键假设：{'；'.join(red['key_assumptions'])}")
            if red.get("permanent_loss_paths"):
                lines.append(f"- 红队永久损失路径：{'；'.join(red['permanent_loss_paths'])}")
            if red.get("verdict"):
                lines.append(f"- 红队结论：{red['verdict']}")

    m11 = results.get("M11_monitor")
    if m11 and m11.outputs.get("monitor_rules"):
        lines += ["", "## 监控规则（M11）", ""]
        for rule in m11.outputs["monitor_rules"]:
            msg = rule.get("message") or rule.get("description") or ""
            lines.append(f"- [{rule['severity']}] {msg}（触发：{rule['trigger']}）")

    lines += ["", "## 假设（assumptions）", "", "```json", _json(session.assumptions), "```",
              "", "## 备忘录质量自检（self_check）", "", "```json", _json(_self_check(session)), "```",
              "", "## 数据来源与免责声明", "", "- 数据快照与模块证据见各模块输出；本备忘录不构成投资建议。"]
    return "\n".join(lines)


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_decision_snapshot(session: Session) -> dict:
    """M10 决策快照（O-3 输出快照审计）：决策结果 + 输入 handoff 摘要，供复盘/审计。

    由工作流引擎在 M10 完成后写入 session.decision_snapshots。
    """
    m10 = session.module_results.get("M10_decision")
    if m10 is None or not m10.outputs:
        return {}

    def _handoff(aid: str, keys: list[str]) -> dict:
        r = session.module_results.get(aid)
        if not r or not r.outputs:
            return {}
        h = r.outputs.get("handoff") or {}
        return {k: h[k] for k in keys if k in h}

    m4 = session.module_results.get("M4_valuation")
    m9 = session.module_results.get("M9_risk")
    return {
        "session_id": session.id,
        "company_code": session.company_code,
        "company_name": session.company_name,
        "created_at": (m10.finished_at or session.created_at).isoformat(),
        "decision_code": m10.outputs.get("decision_code"),
        "total": m10.outputs.get("total"),
        "position": m10.outputs.get("position"),
        "conclusion": m10.outputs.get("conclusion"),
        "blocked_by_veto": m10.outputs.get("blocked_by_veto"),
        "vetoed": m10.outputs.get("vetoed"),
        "dimensions": m10.outputs.get("dimensions"),
        "decision_reasons": (m10.outputs.get("qualitative") or {}).get("decision_reasons", []),
        "handoff": m10.outputs.get("handoff", {}),
        "inputs": {
            "M1_business_model": _handoff("M1_business_model", ["valuation_route", "understandability_level"]),
            "M3_growth": _handoff("M3_growth", ["recommended_growth_rate", "growth_confidence", "cyclicality_flag", "prosperity_code"]),
            "M4_valuation": {
                "intrinsic_value": (m4.outputs.get("intrinsic_value") if m4 else None),
                "current_price": (m4.outputs.get("current_price") if m4 else None),
            },
            "M7_market": _handoff("M7_market", ["market_state", "valuation_percentile", "margin_adjustment", "sentiment_heat"]),
            "M8_safety_margin": _handoff("M8_safety_margin", ["mos_state", "buy_zone", "sell_zone"]),
            "M9_risk": {
                "veto_count": len(m9.outputs.get("vetoes") or []) if m9 else 0,
                "monitor_candidates": (m9.outputs.get("monitor_candidates") if m9 else []),
            },
        },
        "meta": m10.meta,
    }


def _self_check(session: Session) -> dict:
    """备忘录质量自评（O-4，FinRobot 报告三指标）：规则自评，不改变内容。

    - accuracy：关键数值（估值区间/现价）齐全且无降级模块
    - logicality：M10 有结论 + M9 风险清单存在
    - storytelling：完成模块数越多可读性越好
    """
    notes: list[str] = []
    degraded = [aid for aid, r in session.module_results.items() if (r.meta or {}).get("degraded")]
    m4 = session.module_results.get("M4_valuation")
    has_numbers = bool(
        m4 and m4.outputs.get("intrinsic_value") and m4.outputs.get("current_price")
    )
    accuracy = "high" if (has_numbers and not degraded) else ("medium" if has_numbers else "low")
    if degraded:
        notes.append(f"降级模块：{', '.join(degraded)}")
    if not has_numbers:
        notes.append("缺估值区间/现价，数字完整性不足")

    m10 = session.module_results.get("M10_decision")
    m9 = session.module_results.get("M9_risk")
    has_conclusion = bool(m10 and m10.outputs.get("conclusion"))
    has_risks = bool(m9 and m9.outputs.get("risk_items") is not None)
    logicality = "high" if (has_conclusion and has_risks) else "medium"
    if not has_conclusion:
        notes.append("M10 未产出结论，逻辑链不完整")

    n_done = sum(1 for r in session.module_results.values() if r.status == ModuleStatus.DONE)
    storytelling = "high" if n_done >= 9 else ("medium" if n_done >= 5 else "low")
    return {"accuracy": accuracy, "logicality": logicality, "storytelling": storytelling, "notes": notes}
