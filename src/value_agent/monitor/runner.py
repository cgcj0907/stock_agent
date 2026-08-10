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
    user_id: str | None = None  # 规则归属用户（None=全局/系统）；按用户推送时使用
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
    user_id = rule.get("user_id")
    if rule_type in _PRICE_RULES:
        threshold = _rule_price(rule)
        if threshold is None:
            return None
        if rule_type == "price_buy" and price <= threshold:
            return MonitorEvent(code, name or rule_name, "price_buy",
                                f"现价 {price} ≤ 买入区间 {threshold}，可分批建仓", "info",
                                user_id=user_id)
        if rule_type == "price_sell" and price >= threshold:
            return MonitorEvent(code, name or rule_name, "price_sell",
                                f"现价 {price} ≥ 卖出区间 {threshold}，考虑兑现", "warn",
                                user_id=user_id)
        return None
    # 非价格规则：按 _ALERT_RULES 配置的严重度门槛触发（standing 条件，每日复查提醒）
    needed = _ALERT_RULES.get(rule_type)
    if needed is None:
        return None
    if severity not in needed:
        return None
    return MonitorEvent(code, name or rule_name, rule_type, message, severity, user_id=user_id)


def _rules_for_session(session: Session, rules_store) -> list[dict] | None:
    """取某会话的监控规则：优先 monitor_rules 表（规则源），回退会话 JSONB 的 M11 规则。"""
    if rules_store is not None:
        stored = rules_store.list_by_session(session.id)
        if stored:
            return stored
    m11 = session.module_results.get("M11_monitor")
    if m11 and m11.outputs:
        raw = m11.outputs.get("monitor_rules")
        if raw:
            return [r for r in raw if isinstance(r, dict)]
    return None


def run_daily_monitor(
    sessions: list[Session],
    source: DataSource,
    *,
    quarterly_review: bool = False,
    rules_store=None,
) -> list[MonitorEvent]:
    """对已完成会话，用 M11 监控规则（或旧 M8 回退）评估触发条件。

    rules_store：monitor_rules 表存储（可选）。传入时规则以表为准（支持用户编辑），
    表里没有该会话规则再回退会话 JSONB → M8。不传则维持原 JSONB 行为。
    quarterly_review（9.3 财报季自动复查）：True 时对 warn/critical 级非价格 watch
    （景气/财务/风险/决策）补发「财报季复查」提醒事件，覆盖日常只展示在 memo 的复查项。
    """
    events: list[MonitorEvent] = []
    for session in sessions:
        if session.status != SessionStatus.COMPLETED:
            continue
        price = _latest_close(source, session.company_code)
        if price is None:
            continue
        name = session.company_name or session.company_code
        rules = _rules_for_session(session, rules_store)

        if rules:
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                rule = dict(rule)
                rule.setdefault("_code", session.company_code)
                rule.setdefault("_name", name)
                rule.setdefault("user_id", session.user_id)  # 规则归属 → 按用户推送
                ev = _evaluate_rule(rule, price)
                if ev is not None:
                    events.append(ev)
                # 9.3：财报季复查——warn/critical 非价格 watch 生成复查提醒
                if quarterly_review and rule.get("rule_type") not in _PRICE_RULES:
                    sev = rule.get("severity", "info")
                    if sev in ("warn", "critical"):
                        events.append(MonitorEvent(
                            session.company_code, name, rule.get("rule_type", "review"),
                            f"【财报季复查】{rule.get('message') or rule.get('trigger') or ''}",
                            sev,
                        ))
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
                    user_id=session.user_id,
                ))
            elif sell is not None and price >= sell:
                events.append(MonitorEvent(
                    session.company_code, name, "price_sell",
                    f"现价 {price} ≥ 卖出区间 {sell}，考虑兑现", "warn",
                    user_id=session.user_id,
                ))
    # I-2 记忆：把本次命中写入各会话 monitor_hits（跨会话输入供下次分析注入）。
    # 按 (code, rule_type) 去重：同一条规则再次触发时用最新一次覆盖，
    # 避免每日任务重复追加导致 monitor_hits 膨胀、前端时间线刷屏。
    for ev in events:
        for session in sessions:
            if session.company_code == ev.company_code and session.status == SessionStatus.COMPLETED:
                hit = {
                    "code": ev.company_code,
                    "rule_type": ev.rule_type,
                    "message": ev.message,
                    "severity": ev.severity,
                    "occurred_at": ev.occurred_at.isoformat(),
                }
                key = (ev.company_code, ev.rule_type)
                replaced = False
                for existing in session.monitor_hits:
                    if (existing.get("code"), existing.get("rule_type")) == key:
                        existing.update(hit)
                        replaced = True
                        break
                if not replaced:
                    session.monitor_hits.append(hit)
    return events


def _post_webhook(url: str, payload: dict, timeout: float = 10.0) -> tuple[bool, str]:
    """POST 一个 Webhook 载荷，返回 (是否成功, 详情)。飞书 code / 企微 errcode 为 0 才算成功。"""
    try:
        import httpx

        resp = httpx.post(url, json=payload, timeout=timeout)
        data = resp.json()
        code = data.get("code", data.get("errcode"))
        ok = code in (0, "0")
        detail = str(data.get("msg") or data.get("errmsg") or f"HTTP {resp.status_code}")
        return ok, detail
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _events_text(events: list[MonitorEvent]) -> str:
    return "\n".join(f"[{e.severity}] {e.company_name}({e.company_code}) {e.message}" for e in events)


def _payloads_for_env(text: str) -> list[tuple[str, str, dict]]:
    """全局渠道（环境变量 FEISHU_WEBHOOK / WECHAT_WEBHOOK）。"""
    payloads: list[tuple[str, str, dict]] = []
    if os.getenv("FEISHU_WEBHOOK"):
        payloads.append(("飞书", os.environ["FEISHU_WEBHOOK"], {"msg_type": "text", "content": {"text": text}}))
    if os.getenv("WECHAT_WEBHOOK"):
        payloads.append(("企业微信", os.environ["WECHAT_WEBHOOK"], {"msgtype": "text", "text": {"content": text}}))
    return payloads


def _payloads_for_channels(channels: dict[str, str], text: str) -> list[tuple[str, str, dict]]:
    """某用户配置的渠道（user_webhooks 表）。"""
    payloads: list[tuple[str, str, dict]] = []
    for channel, url in channels.items():
        if channel == "feishu":
            payloads.append(("飞书", url, {"msg_type": "text", "content": {"text": text}}))
        elif channel == "wechat":
            payloads.append(("企业微信", url, {"msgtype": "text", "text": {"content": text}}))
    return payloads


def _post_payloads(payloads: list[tuple[str, str, dict]]) -> list[str]:
    sent: list[str] = []
    for name, url, payload in payloads:
        ok, detail = _post_webhook(url, payload)
        if ok:
            sent.append(name)
            logger.info("已推送 %s", name)
        else:
            logger.warning("推送 %s 失败：%s", name, detail)
    return sent


def send_webhook_text(text: str) -> list[str]:
    """向全局配置的飞书/企业微信 Webhook 推送一条文本消息，返回成功渠道名列表。"""
    return _post_payloads(_payloads_for_env(text))


def send_webhook_to_channels(channels: dict[str, str], text: str) -> list[str]:
    """向指定渠道 {channel: webhook_url} 推送一条文本消息（用户通知配置用）。"""
    return _post_payloads(_payloads_for_channels(channels, text))


def notify_webhooks(events: list[MonitorEvent], webhook_store=None) -> list[str]:
    """推送到飞书/企业微信 Webhook，返回成功渠道名列表；无事件时不推送。

    - webhook_store 为空（默认）→ 全局：环境变量 FEISHU_WEBHOOK / WECHAT_WEBHOOK
    - 传入 UserWebhookStore → 按事件归属 user_id 分组推送：
        归属用户的事件 → 推该用户 user_webhooks 里配置的渠道（没配则跳过）；
        全局事件（user_id=None）→ 仍走环境变量。
    """
    if not events:
        return []
    if webhook_store is None:
        return send_webhook_text(_events_text(events))

    by_user: dict[str | None, list[MonitorEvent]] = {}
    for e in events:
        by_user.setdefault(e.user_id, []).append(e)

    sent: list[str] = []
    for user_id, evs in by_user.items():
        text = _events_text(evs)
        if user_id is None:
            sent += send_webhook_text(text)
            continue
        try:
            channels = webhook_store.get_webhooks(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取用户 %s webhook 失败：%s", user_id, exc)
            channels = {}
        if not channels:
            logger.info("用户 %s 未配置通知渠道，跳过推送", user_id)
            continue
        sent += _post_payloads(_payloads_for_channels(channels, text))
    return sent
