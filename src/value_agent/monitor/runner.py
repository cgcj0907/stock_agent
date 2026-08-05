"""每日监控运行器：对已完成会话评估价格触发条件并推送事件。

调用：python -m value_agent monitor --daily（由 GitHub Actions 每日触发，docs/07 §1.7）。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

from value_agent.data.sources.base import DataSource
from value_agent.sessions.models import Session, SessionStatus

logger = logging.getLogger(__name__)


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


def run_daily_monitor(sessions: list[Session], source: DataSource) -> list[MonitorEvent]:
    """对已完成会话，用最新价评估买入/卖出触发。"""
    events: list[MonitorEvent] = []
    for session in sessions:
        if session.status != SessionStatus.COMPLETED:
            continue
        m8 = session.module_results.get("M8_safety_margin")
        if m8 is None or not m8.outputs.get("buy_price"):
            continue
        price = _latest_close(source, session.company_code)
        if price is None:
            continue
        buy = m8.outputs["buy_price"]
        sell = m8.outputs.get("sell_price")
        name = session.company_name or session.company_code
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
