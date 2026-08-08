"""M6 治理与资本配置引擎：以分红持续性/回报股东倾向做确定性代理评估。

规则层证据 = 分红代理（连续分红年数 + 每股派息趋势）+ 可选治理事件
（质押/减持/监管处罚/审计变更/并购回报/回购）。事件数据源未接入时按中性处理，
不臆测治理结论；接入后作为「非分红证据」进入评分与结构化风险码。
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

# 治理事件 → (风险码, 中文标签, 严重度, 扣分)
# 规则层非分红证据：事件数据由数据源经 governance_events 提供（见 data/sources/base.py）
_EVENT_RULES: dict[str, tuple[str, str, str, int]] = {
    "pledges": ("SHARE_PLEDGE", "股权质押", "medium", 15),
    "reductions": ("SHARE_REDUCTION", "股东/高管减持", "medium", 15),
    "regulatory": ("REGULATORY_PENALTY", "监管处罚/问询", "high", 15),
    "auditor_changes": ("AUDITOR_CHANGE", "审计机构变更", "medium", 10),
    "acquisitions": ("CAPITAL_IMPAIRMENT", "并购回报不佳", "medium", 10),
    # 6.2：股权集中度（前十大股东合计比例）——极高度集中给低 severity 风险码（信息 + LLM 定性）
    "control": ("CONTROL_RISK", "股权集中度", "low", 5),
}
_EVENT_DEDUCTION_CAP = 40  # 事件扣分封顶，避免单一证据主导评分

# 6.4：质押/减持比例分级阈值（超阈值升级 high + 加扣）
_PLEDGE_HIGH_RATIO = 0.5    # 质押比例 > 50% → high
_REDUCTION_HIGH_RATIO = 0.05  # 减持比例 > 5% → high
# 6.5：高危治理风险码 → veto_candidate 白名单（M9/M11 长期监控候选）
_VETO_CANDIDATE_CODES: frozenset[str] = frozenset({"REGULATORY_PENALTY", "SHARE_PLEDGE"})


@dataclass
class GovernanceResult:
    score: float
    dividend_years: int
    payout_latest: float | None
    note: str
    dividend_yield: float | None = None  # TTM 每股派息 ÷ 现价（股息率）
    evidence: list[str] = field(default_factory=list)
    # 规则层治理事件 → 结构化风险码 [{code, severity, description}]（M9 消费）
    risk_codes: list[dict] = field(default_factory=list)


def _normalize_events(events: dict) -> dict[str, list]:
    """数据源事件归一化为 {类别: [事件]}。

    兼容两种形状：records + kind 字段（数据源约定），或顶层类别键
    {regulatory: [...], buybacks: [...]}。records 存在时优先用 records。
    """
    out: dict[str, list] = {k: [] for k in _EVENT_RULES}
    out["buybacks"] = []
    recs = events.get("records")
    if recs:
        for r in recs:
            if not isinstance(r, dict):
                continue
            k = r.get("kind")
            if k in out:
                out[k].append(r)
    else:
        for k in out:
            out[k] = list(events.get(k) or [])
    return out


def _event_brief(label: str, ev: dict) -> str:
    """事件摘要：{holder, period/date} 有则带上，防止重复堆砌空字段。"""
    if not isinstance(ev, dict):
        return label
    bits = [label]
    for key in ("holder", "period", "date", "reason"):
        v = ev.get(key)
        if isinstance(v, str) and v.strip():
            bits.append(v.strip())
    return "；".join(bits)


def _period_date(period: str) -> datetime.date | None:
    """把 'YYYYMMDD' 财报期转 date（避免 naive datetime 构造，DTZ007）。"""
    try:
        return datetime.date(int(period[:4]), int(period[4:6]), int(period[6:8]))
    except (TypeError, ValueError, IndexError):
        return None


def _ttm_dividend(records: list[dict], anchor: datetime.date) -> float:
    """最近 12 个月（截至最新分红报告期）的每股派息合计（TTM 口径）。"""
    start = anchor - datetime.timedelta(days=365)
    total = 0.0
    for r in records:
        try:
            d = _period_date(str(r.get("period")))
            if d is None:
                continue
        except (TypeError, ValueError):
            continue
        if start < d <= anchor:  # 开区间：避免把整一年前的年报重复计入
            v = r.get("cash_div_tax")
            if isinstance(v, (int, float)):
                total += float(v)
    return round(total, 4)


def assess_governance(
    dividends: dict,
    events: dict | None = None,
    price: float | None = None,
) -> GovernanceResult:
    """输入分红记录（+ 可选治理事件），输出治理/回报股东评分。

    代理：连续分红年数 + 每股派息趋势（基础）；
    治理事件（非分红证据）：质押/减持/监管处罚/审计变更/并购回报不佳扣分，
    持续回购加分，并映射为结构化 risk_codes 供 M9 消费。
    events 为 None 表示事件数据源未接入；为 dict（可全空）表示已接入但无事件。
    price 为现价（元），用于计算股息率 = TTM 每股派息 ÷ 现价；缺失时股息率置 None。
    """
    recs = sorted(
        (r for r in dividends.get("records", []) if r.get("period")),
        key=lambda r: r["period"], reverse=True,
    )
    payouts = [r["cash_div_tax"] for r in recs if r.get("cash_div_tax") is not None]

    if not recs:
        evidence = ["无分红数据，无法评估回报股东倾向"]
        if events is not None:
            evidence.append("暂无治理事件数据，治理按中性计")
        return GovernanceResult(
            score=50.0, dividend_years=0, payout_latest=None,
            note="无分红数据，治理按中性计", evidence=evidence,
        )

    years = len(recs)
    score = 40.0 + min(years * 5, 30)  # 连续分红年数
    latest = payouts[0] if payouts else None
    if len(payouts) >= 2 and payouts[0] > payouts[1]:
        score += 15
        note = "分红连续且递增（回报股东意愿强）"
    elif payouts:
        score += 8
        note = "有持续分红"
    else:
        note = "有分红预案但无派息数据"

    evidence = [f"连续分红 {years} 期；最新每股派息 {latest} 元", note]

    # 股息率：TTM 每股派息（最近 12 个月）÷ 现价
    dividend_yield: float | None = None
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None
    if price and price > 0 and recs:
        try:
            anchor = _period_date(str(recs[0]["period"]))
            ttm = _ttm_dividend(recs, anchor) if anchor is not None else 0.0
        except (TypeError, ValueError):
            ttm = 0.0
        if ttm > 0:
            dividend_yield = round(ttm / price, 4)
            evidence.append(
                f"股息率（TTM 每股派息 {ttm} 元 ÷ 现价 {price} 元）= {dividend_yield:.2%}"
            )

    risk_codes: list[dict] = []

    if events is None:
        # 事件数据源未接入：如实标注代理边界，不臆测
        evidence.append("⚠️ 股权结构/质押/减持/回购等治理事件待接入后补充")
    else:
        norm = _normalize_events(events)
        found = False
        deduction = 0
        for key, (code, label, sev, penalty) in _EVENT_RULES.items():
            recs_ev = norm[key]
            if not recs_ev:
                continue
            found = True
            deduction += penalty
            entry: dict = {
                "code": code,
                "severity": sev,
                "description": f"{label}：{_event_brief(label, recs_ev[0])}",
            }
            # 质押等事件带比率时透传给 M9（质押率 > 80% 否决规则用），LLM 风险码无 ratio 不触发
            ratio: float | None = None
            if isinstance(recs_ev[0], dict):
                ratio = recs_ev[0].get("ratio")
                try:
                    ratio = float(ratio) if ratio is not None else None
                except (TypeError, ValueError):
                    ratio = None
            if ratio is not None:
                entry["ratio"] = ratio
            # 6.4：比例分级——质押 >50% / 减持 >5% 升级 high 并加扣（30% 与 80% 治理含义不同）
            if ratio is not None:
                if code == "SHARE_PLEDGE" and ratio > _PLEDGE_HIGH_RATIO:
                    entry["severity"] = "high"
                    deduction += 10
                    entry["description"] += f"（质押比例 {ratio:.0%} > 50%，风险升级）"
                elif code == "SHARE_REDUCTION" and ratio > _REDUCTION_HIGH_RATIO:
                    entry["severity"] = "high"
                    deduction += 10
                    entry["description"] += f"（减持比例 {ratio:.0%} > 5%，风险升级）"
            # 6.5：高危治理码 → veto_candidate（M9 标记、M11 长期监控）
            if entry["severity"] == "high" and code in _VETO_CANDIDATE_CODES:
                entry["veto_candidate"] = True
            risk_codes.append(entry)
            evidence.append(f"治理事件：{label}（{len(recs_ev)} 条）")
        buybacks = norm["buybacks"]
        if len(buybacks) >= 2:
            found = True
            score += 10
            evidence.append(f"治理事件：持续回购（{len(buybacks)} 期）")
        if deduction:
            score -= min(deduction, _EVENT_DEDUCTION_CAP)
        if not found:
            evidence.append("暂无治理事件数据（质押/减持/回购/监管/审计），按中性计")

    score = round(max(0.0, min(score, 100.0)), 1)
    return GovernanceResult(
        score=score, dividend_years=years, payout_latest=latest,
        note=note, dividend_yield=dividend_yield,
        evidence=evidence, risk_codes=risk_codes,
    )
