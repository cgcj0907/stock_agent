"""每日任务：读监控规则 → 实时拉价判断 → 命中写回会话（monitor_hits）→ Webhook 推送（FC 定时触发器同款逻辑）。

两条入口复用同一实现：
- CLI：`value-agent daily`（本地/容器手动跑）
- FastAPI：`POST /api/daily`（阿里云 FC 定时触发器调用，大陆 IP 拉 AkShare）

数据流：读已完成会话 + monitor_rules 表 → 按规则里的代码**实时拉最新价**（AkShare，大陆 IP）
→ 评估触发 → 命中**写回会话 monitor_hits**（前端监控中心可读 + 跨会话记忆）→ 按用户推送飞书/企业微信。
**不写行情/估值数据**（Supabase 只写 monitor_hits）。
依赖可注入，便于测试。
"""
from __future__ import annotations

import logging

from value_agent.data.manager import _default_source
from value_agent.monitor.rules_store import create_rule_store
from value_agent.monitor.runner import notify_webhooks, run_daily_monitor
from value_agent.monitor.user_webhooks import create_user_webhook_store
from value_agent.sessions import create_session_store

logger = logging.getLogger(__name__)


def run_daily_job(
    *,
    quarterly_review: bool = False,
    source=None,
    store=None,
    rules_store=None,
    webhook_store=None,
) -> dict:
    """执行一次每日任务（只读），返回汇总 dict。

    读已完成会话 + monitor_rules 表；价格来自实时源（按规则代码拉最新价），
    命中写回会话 monitor_hits（不写行情/估值）。默认按环境配置创建真实组件并 close；测试可注入替身。
    """
    source = source or _default_source()
    store = store or create_session_store()
    rules_store = rules_store or create_rule_store()
    webhook_store = webhook_store or create_user_webhook_store()
    errors: list[str] = []
    try:
        # 1) 监控评估：规则以 monitor_rules 表为准（回退会话 JSONB → M8），
        #    价格按规则代码实时拉取（只读，不写库）
        try:
            sessions = store.list()
            events = run_daily_monitor(
                sessions, source,
                quarterly_review=quarterly_review,
                rules_store=rules_store,
            )
        except Exception as exc:
            logger.exception("daily 监控评估失败")
            errors.append(f"监控评估失败：{exc}")
            sessions, events = [], []

        # 2) I-2 记忆闭环：命中写回会话存储（与 CLI `monitor --daily` 一致），
        #    前端监控中心「命中记录」与跨会话记忆才能读到；不写行情/估值。
        try:
            for session in sessions:
                if session.monitor_hits:
                    store.save(session)
        except Exception as exc:
            logger.exception("daily 命中写回失败")
            errors.append(f"命中写回失败：{exc}")

        # 3) Webhook 推送：按事件归属用户推送（user_id=None 走全局环境变量）
        pushed = notify_webhooks(events, webhook_store=webhook_store) if events else []
        return {
            "updated": {},  # 只读模式：不写行情/估值
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
        _close(store)
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
