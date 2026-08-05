"""投资备忘录生成：从会话结果组装 markdown 备忘录（docs/01-design.md §6）。"""
from __future__ import annotations

import json

from value_agent.sessions.models import Session


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
            lines.append(
                f"- 内在价值区间：{iv['low']} ~ {iv['high']} 元（中值 {iv['mid']}），"
                f"现价 {m4.outputs.get('current_price')} 元"
            )
        if m8 and m8.outputs.get("buy_price"):
            lines.append(
                f"- 安全边际：买入 ≤ {m8.outputs['buy_price']} 元 / 卖出 ≥ {m8.outputs['sell_price']} 元"
                f"（{m8.outputs['status']}）"
            )
        if m10.outputs.get("vetoed"):
            lines.append(f"- ⚠️ 否决项：{m10.outputs['vetoed']}")
    else:
        lines.append("- 结论：M10 未产出（评分卡未执行）")

    lines += ["", "## 模块执行结果", "", "| 模块 | 状态 | 评分 | 证据数 |", "|---|---|---|---|"]
    for agent_id in sorted(results):
        r = results[agent_id]
        lines.append(
            f"| {r.module} | {r.status.value} | "
            f"{r.score if r.score is not None else '—'} | {len(r.evidence)} |"
        )

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

    m11 = results.get("M11_monitor")
    if m11 and m11.outputs.get("monitor_rules"):
        lines += ["", "## 监控规则（M11）", ""]
        for rule in m11.outputs["monitor_rules"]:
            lines.append(f"- [{rule['severity']}] {rule['description']}（触发：{rule['trigger']}）")

    lines += ["", "## 假设（assumptions）", "", "```json", _json(session.assumptions), "```",
              "", "## 数据来源与免责声明", "", "- 数据快照与模块证据见各模块输出；本备忘录不构成投资建议。"]
    return "\n".join(lines)


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
