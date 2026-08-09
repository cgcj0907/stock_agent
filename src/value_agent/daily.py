"""每日任务：数据更新 + 监控评估 + Webhook 推送（FC 定时触发器同款逻辑）。

两条入口复用同一实现：
- CLI：`value-agent daily`（本地/容器手动跑）
- FastAPI：`POST /api/daily`（阿里云 FC 定时触发器调用，大陆 IP 拉 AkShare）

数据流：AkShare（大陆 IP）→ 行情/估值入库 → 读已完成会话 + monitor_rules 表
评估触发 → 命中推送飞书/企业微信。依赖可注入，便于测试。
"""
from __future__ import annotations

import logging

from value_agent.core.config import load_settings
from value_agent.core.watchlist import load_watchlist
from value_agent.data.manager import _default_source
from value_agent.data.pipelines.ingest import daily_update
from value_agent.data.storage.factory import create_storage
from value_agent.monitor.rules_store import create_rule_store
from value_agent.monitor.runner import notify_webhooks, run_daily_monitor
from value_agent.monitor.user_webhooks import create_user_webhook_store
from value_agent.sessions import create_session_store

logger = logging.getLogger(__name__)


def run_daily_job(
    *,
    lookback_days: int = 10,
    quarterly_review: bool = False,
    storage=None,
    source=None,
    store=None,
    rules_store=None,
    webhook_store=None,
    codes: list[str] | None = None,
) -> dict:
    """执行一次每日任务，返回汇总 dict。

    默认按环境配置创建真实组件（storage/source/session store/rules store/webhook store）；
    测试可注入替身。任务结束会 close 创建出来的存储。
    """
    created_storage = storage is None
    storage = storage or create_storage(load_settings())
    source = source or _default_source()
    store = store or create_session_store()
    rules_store = rules_store or create_rule_store()
    webhook_store = webhook_store or create_user_webhook_store()
    errors: list[str] = []
    try:
        # 1) 数据更新：行情/估值增量入库（AkShare → Supabase/SQLite）
        #    失败不中断：监控继续用 Supabase 缓存行情（海外/数据源抖动时降级）
        codes = codes if codes is not None else load_watchlist()
        try:
            updated = daily_update(storage, source, codes, lookback_days=lookback_days)
        except Exception as exc:
            logger.exception("daily 数据更新失败（继续用缓存行情做监控）")
            errors.append(f"数据更新失败：{exc}")
            updated = {"daily_price": 0, "valuation_history": 0, "skipped": 0, "error": str(exc)}

        # 2) 监控评估：规则以 monitor_rules 表为准（回退会话 JSONB → M8）
        try:
            sessions = store.list()
            events = run_daily_monitor(
                sessions, source,
                quarterly_review=quarterly_review,
                rules_store=rules_store,
            )
            # I-2 记忆闭环：命中写回会话
            for session in sessions:
                if session.monitor_hits:
                    store.save(session)
        except Exception as exc:
            logger.exception("daily 监控评估失败")
            errors.append(f"监控评估失败：{exc}")
            sessions, events = [], []

        # 3) Webhook 推送：按事件归属用户推送（user_id=None 走全局环境变量）
        pushed = notify_webhooks(events, webhook_store=webhook_store) if events else []
        return {
            "updated": updated,
            "session_count": len(sessions),
            "monitor_events": len(events),
            "events": [
                {
                    "severity": e.severity,
                    "rule_type": e.rule_type,
                    "company_code": e.company_code,
                    "company_name": e.company_name,
                    "message": e.message,
                }
                for e in events
            ],
            "pushed_channels": pushed,
            "errors": errors,
        }
    finally:
        if created_storage:
            _close(storage)
        _close(rules_store)
        _close(webhook_store)


def _close(obj) -> None:
    close = getattr(obj, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        logger.debug("关闭 %s 失败", type(obj).__name__, exc_info=True)
