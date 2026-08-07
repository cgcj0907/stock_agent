"""每日监控运行器：对已完成会话评估监控规则触发条件并推送事件。

调用：python -m value_agent monitor --daily（由 GitHub Actions 每日触发，docs/07 §1.7）。

9.1（backlog）：runner 消费 M11 生成的 `monitor_rules`（price_buy/price_sell 用
params.price 阈值评估；decision_watch 否决 → 提醒；critical 级非价格 watch → 独立告警），
不再另写一份 M8 价格逻辑。旧会话（无 M11 规则）回退 M8 buy/sell 保持兼容。
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from value_agent.data.sources.base import DataSource
from value_agent.sessions.models import Session, SessionStatus

logger = logging.getLogger(__name__)

# 价格类规则（需最新价评估）
_PRICE_RULES = {"price_buy", "price_sell"}
# 触发即告警的严重 watch（非价格、可执行路径：9.2 / 8.4）
_ALERT_RULES = {
    "decision_watch": ("warn",),        # 一票否决解除前不建仓提醒
    "risk_watch": ("critical",),        # critical 级风险项独立告警
    "fundamental_watch": ("critical",),  # critical 级财务信号告警
    "valuation_sell": ("warn",),        # 估值过热卖出参考
    "mos_watch": ("warn",),             # 估值偏高暂停买入
}


@dataclass
class MonitorEvent:
    company_code: str
    company_name: str
    rule_type: str
    message: str
    severity: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _latest_close(source: DataSource, code: str) -> float | None:
    try:
        recs = source.daily_prices(code)["records"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("获取 %s 行情失败：%s", code, exc)
        return None
    if not recs:
        return None
    latest = max(recs, key=lambda r: r.get("trade_date") or "")
    return latest.get("close")


def _rule_price(rule: dict) -> float | None:
    """规则阈值：优先 params.price（结构化），回退解析 trigger 文本。"""
    params = rule.get("params") or {}
    if isinstance(params, dict) and params.get("price") is not None:
        try:
            return float(params["price"])
        except (TypeError, ValueError):
            pass
    m = re.search(r"([\d.]+)\s*元", str(rule.get("trigger") or ""))
    return float(m.group(1)) if m else None


def _evaluate_rule(rule: dict, price: float) -> MonitorEvent | None:
    """对单条规则评估是否触发（价格类用最新价；非价格类按严重度/参数）。"""
    rule_type = rule.get("rule_type", "")
    severity = rule.get("severity", "info")
    name, message = "", rule.get("message") or rule.get("description") or rule.get("trigger") or ""
    code, rule_name = rule.get("_code", ""), rule.get("_name", "")
    if rule_type in _PRICE_RULES:
        threshold = _rule_price(rule)
        if threshold is None:
            return None
        if rule_type == "price_buy" and price <= threshold:
            return MonitorEvent(code, name or rule_name, "price_buy",
                                f"现价 {price} ≤ 买入区间 {threshold}，可分批建仓", "info")
        if rule_type == "price_sell" and price >= threshold:
            return MonitorEvent(code, name or rule_name, "price_sell",
                                f"现价 {price} ≥ 卖出区间 {threshold}，考虑兑现", "warn")
        return None
    # 非价格规则：按 _ALERT_RULES 配置的严重度门槛触发（standing 条件，每日复查提醒）
    needed = _ALERT_RULES.get(rule_type)
    if needed is None:
        return None
    if severity not in needed:
        return None
    return MonitorEvent(code, name or rule_name, rule_type, message, severity)


def run_daily_monitor(sessions: list[Session], source: DataSource) -> list[MonitorEvent]:
    """对已完成会话，用 M11 监控规则（或旧 M8 回退）评估触发条件。"""
    events: list[MonitorEvent] = []
    for session in sessions:
        if session.status != SessionStatus.COMPLETED:
            continue
        price = _latest_close(source, session.company_code)
        if price is None:
            continue
        name = session.company_name or session.company_code
        rules = (session.module_results.get("M11_monitor") or {}).outputs.get("monitor_rules") \
            if session.module_results.get("M11_monitor") else None

        if rules:
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                rule = dict(rule)
                rule.setdefault("_code", session.company_code)
                rule.setdefault("_name", name)
                ev = _evaluate_rule(rule, price)
                if ev is not None:
                    events.append(ev)
        else:
            # 旧会话回退：无 M11 规则时用 M8 buy/sell（历史行为）
            m8 = session.module_results.get("M8_safety_margin")
            if m8 is None or not m8.outputs.get("buy_price"):
                continue
            buy = m8.outputs["buy_price"]
            sell = m8.outputs.get("sell_price")
            if price <= buy:
                events.append(MonitorEvent(
                    session.company_code, name, "price_buy",
                    f"现价 {price} ≤ 买入区间 {buy}，可分批建仓", "info",
                ))
            elif sell is not None and price >= sell:
                events.append(MonitorEvent(
                    session.company_code, name, "price_sell",
                    f"现价 {price} ≥ 卖出区间 {sell}，考虑兑现", "warn",
                ))
    # I-2 记忆：把本次命中写入各会话 monitor_hits（跨会话输入供下次分析注入）
    for ev in events:
        for session in sessions:
            if session.company_code == ev.company_code and session.status == SessionStatus.COMPLETED:
                session.monitor_hits.append({
                    "code": ev.company_code,
                    "rule_type": ev.rule_type,
                    "message": ev.message,
                    "severity": ev.severity,
                    "occurred_at": ev.occurred_at.isoformat(),
                })
    return events


def notify_webhooks(events: list[MonitorEvent]) -> None:
    """推送到飞书/企业微信 Webhook（环境变量 FEISHU_WEBHOOK / WECHAT_WEBHOOK）。"""
    if not events:
        return
    text = "\n".join(f"[{e.severity}] {e.company_name}({e.company_code}) {e.message}" for e in events)
    payloads = []
    if os.getenv("FEISHU_WEBHOOK"):
        payloads.append((os.environ["FEISHU_WEBHOOK"], {"msg_type": "text", "content": {"text": text}}))
    if os.getenv("WECHAT_WEBHOOK"):
        payloads.append((os.environ["WECHAT_WEBHOOK"], {"msgtype": "text", "text": {"content": text}}))
    for url, payload in payloads:
        try:
            import httpx

            httpx.post(url, json=payload, timeout=10)
            logger.info("已推送 %s", url[:40])
        except Exception as exc:  # noqa: BLE001
            logger.warning("推送失败：%s", exc)
