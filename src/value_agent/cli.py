"""命令行入口：python -m value_agent <command>

命令：
  analyze CODE [--workflow id] [--memo path] [--store memory|sqlite|supabase]
  sessions list
  agents list
  workflows list
  data init | update --daily
  monitor --daily
  serve [--host H] [--port P]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from value_agent.agents import AgentRegistry
from value_agent.agents.builtin import register_builtin_agents
from value_agent.core.config import load_settings
from value_agent.core.llm import get_llm
from value_agent.core.watchlist import load_watchlist
from value_agent.daily import run_daily_job
from value_agent.data.manager import DataManager, _default_source
from value_agent.data.pipelines.ingest import daily_update, ingest_company
from value_agent.data.storage.factory import create_storage
from value_agent.monitor.rules_store import create_rule_store
from value_agent.monitor.runner import notify_webhooks, run_daily_monitor
from value_agent.monitor.user_webhooks import create_user_webhook_store
from value_agent.report.memo import build_memo
from value_agent.sessions import InMemoryStore, SessionManager, SqliteStore, create_session_store
from value_agent.workflow import WorkflowEngine, default_workflow

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

def _make_store(kind: str):
    if kind == "sqlite":
        settings = load_settings()
        path = settings.get("storage", {}).get("path", "data/sessions.db")
        return SqliteStore(path)
    if kind == "supabase":
        dsn = os.getenv("DATABASE_URL", "")
        if not dsn:
            raise SystemExit("--store supabase 需要 DATABASE_URL（.env 或环境变量）")
        from value_agent.sessions.supabase_store import SupabaseStore

        return SupabaseStore(dsn)
    return InMemoryStore()


def _load_workflow(workflow_id: str):
    if workflow_id == "default":
        return default_workflow()
    try:
        from value_agent.workflow import load_workflow_from_yaml

        return load_workflow_from_yaml(f"config/workflows/{workflow_id}.yaml")
    except FileNotFoundError:
        raise SystemExit(f"工作流不存在: {workflow_id}（可用: default）") from None
    except ImportError as exc:
        raise SystemExit(
            f"加载 YAML 工作流需要 pyyaml（先执行 `uv sync` 安装依赖）：{exc}"
        ) from None


def _sync_to_storage(storage, from_db: str | None) -> None:
    """把本地 sqlite 库同步到目标存储（如 Supabase），按 code 批量 upsert。"""
    from value_agent.data.storage.sqlite_storage import SqliteMarketStorage

    path = from_db or "data/market.db"
    src = SqliteMarketStorage(path)
    tables = ("company", "financials", "daily_price", "valuation_history", "dividends")
    total = 0
    try:
        for table in tables:
            records = src.all_records(table)
            records.sort(key=lambda r: str(r.get("code", "")))
            from itertools import groupby

            for code, group in groupby(records, key=lambda r: str(r.get("code", ""))):
                if not code:
                    continue
                n = storage.upsert(table, code, list(group))
                total += n
            print(f"[sync] {table:<18} {len(records)} 条")
    finally:
        src.close()
    print(f"[data] 同步完成：{path} → {storage.name}，共 {total} 条")


def _validate_stored(storage) -> None:
    """校验已入库数据：逐表输出有效/无效统计与前 3 条问题。"""
    from value_agent.data.validate import validate_table

    for table in ("financials", "daily_price", "valuation_history", "dividends"):
        records = storage.all_records(table)
        report = validate_table(table, records)
        print(f"[validate] {table:<18} 有效 {report.valid}/{report.total}")
        for issue in report.issues[:3]:
            print(f"           ✗ {issue['message']}")
    print("[validate] 校验完成")


def _ping_sources() -> None:
    """逐个实测数据源连通性（部署到 Render 后跑：python -m value_agent data ping）。"""
    import time

    name = "akshare"
    t0 = time.time()
    try:
        from value_agent.data.sources.akshare_source import AkShareDataSource

        src = AkShareDataSource()
        info = src.company_info("600519")
        print(f"[ping] {name:<8} OK ({time.time() - t0:.2f}s) {info.get('name')}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ping] {name:<8} FAIL ({time.time() - t0:.2f}s) {type(exc).__name__}: {str(exc)[:60]}")


def _make_rule_store(kind: str):
    """按 store 类型创建监控规则存储（与 _make_store 同路径/同 DSN，保证落到同一库）。"""
    from value_agent.monitor.rules_store import (
        InMemoryRuleStore,
        SqliteRuleStore,
        SupabaseRuleStore,
    )

    if kind == "sqlite":
        settings = load_settings()
        path = settings.get("storage", {}).get("path", "data/sessions.db")
        return SqliteRuleStore(path)
    if kind == "supabase":
        dsn = os.getenv("DATABASE_URL", "")
        if not dsn:
            raise SystemExit("--store supabase 需要 DATABASE_URL（.env 或环境变量）")
        return SupabaseRuleStore(dsn)
    return InMemoryRuleStore()


def _engine(store_kind: str = "memory") -> tuple[SessionManager, WorkflowEngine]:
    store = _make_store(store_kind)
    manager = SessionManager(store, rules_store=_make_rule_store(store_kind))
    registry = register_builtin_agents(AgentRegistry())
    return manager, WorkflowEngine(registry, manager, data=DataManager(), llm=get_llm())


# ---- 命令实现 ----
def cmd_analyze(args: argparse.Namespace) -> int:
    manager, engine = _engine(args.store)
    data = DataManager()
    info = data.company_info(args.code)
    try:
        session = manager.create_session(
            args.code,
            company_name=info.get("name", ""),
            workflow_id=args.workflow,
            monitor_hits=manager.prior_monitor_hits(args.code),
        )
    except ValueError as exc:
        print(f"[error] {exc}")
        return 1
    session.data_snapshot_id = f"snap_{args.code}_{session.created_at:%Y%m%d%H%M%S}"
    manager.persist(session)
    flow = _load_workflow(args.workflow)
    engine.run(session, flow)
    memo = build_memo(session)
    print(memo)
    if args.memo:
        with open(args.memo, "w", encoding="utf-8") as f:
            f.write(memo)
        print(f"\n[ok] 备忘录已写入 {args.memo}")
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    manager, _ = _engine(args.store)
    for s in manager._store.list():
        print(f"{s.id}  {s.company_code} {s.company_name:<8} {s.status.value}  {s.workflow_id}")
    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    registry = register_builtin_agents(AgentRegistry())
    for spec in registry.specs():
        print(f"{spec.id:<28} {spec.name:<12} requires_llm={spec.requires_llm}")
    return 0


def cmd_workflows(args: argparse.Namespace) -> int:
    print("default  （标准价值投资分析：M1–M11）")
    import glob
    import os

    for path in sorted(glob.glob("config/workflows/*.yaml")):
        print(f"{os.path.basename(path)[:-5]}  （config/workflows/{os.path.basename(path)}）")
    return 0


def cmd_data(args: argparse.Namespace) -> int:
    # 无需存储/数据源的动作：先短路，避免污染输出
    if args.action == "ddl":
        from value_agent.data.storage.base import generate_pg_ddl

        print(generate_pg_ddl())
        return 0
    if args.action == "ping":
        _ping_sources()
        return 0

    settings = load_settings()
    storage = create_storage(settings, backend=args.backend)
    source = _default_source()
    print(f"[data] 数据源: {source.name} | 存储: {storage.name}")
    try:
        if args.action == "init":
            codes = load_watchlist()
            print(f"[data] 全量初始化 {len(codes)} 家公司 ...")
            total = sum(ingest_company(storage, source, code) for code in codes)
            print(f"[data] 完成，共写入 {total} 条记录")
        elif args.action == "update":
            codes = load_watchlist()
            print(f"[data] 每日增量更新 {len(codes)} 家公司 ...")
            stats = daily_update(storage, source, codes, lookback_days=args.days)
            print(f"[data] 完成：行情 +{stats['daily_price']} / 估值 +{stats['valuation_history']} / 跳过 {stats['skipped']}")
        elif args.action == "fetch":
            if not args.code:
                raise SystemExit("[data] fetch 需要股票代码，如：value-agent data fetch 600519")
            print(f"[data] 全量预取 {args.code} → {storage.name} ...")
            n = ingest_company(storage, source, args.code)
            print(f"[data] {args.code} 写入 {n} 条")
        elif args.action == "status":
            print(f"[data] 存储统计: {storage.stats()}")
        elif args.action == "validate":
            _validate_stored(storage)
        elif args.action == "snapshot":
            from value_agent.data.snapshots import create_snapshot, snapshot_summary

            snap = create_snapshot(storage, args.code, as_of=args.as_of)
            print(f"[data] 快照: {snapshot_summary(snap)}")
        elif args.action == "sync":
            _sync_to_storage(storage, args.from_db)
    finally:
        storage.close()
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """每日监控：加载已完成会话 → 最新价评估买卖触发 → 推送。"""
    # 9.9：会话存储与生产一致（SESSION_STORE / DATABASE_URL / SESSIONS_DB），
    # 不再硬编码本地 SqliteStore，避免 GitHub Actions 全新 runner 读不到生产会话
    store = create_session_store()
    rules_store = create_rule_store()
    webhook_store = create_user_webhook_store()
    sessions = store.list()
    source = _default_source()
    print(f"[monitor] 数据源: {source.name} | 已完成会话 {sum(1 for s in sessions if s.status.value == 'completed')} 个")
    events = run_daily_monitor(
        sessions, source,
        quarterly_review=bool(getattr(args, "quarterly", False)),
        rules_store=rules_store,
    )
    for e in events:
        print(f"[monitor] [{e.severity}] {e.company_name}({e.company_code}) {e.message}")
    # I-2 记忆闭环：命中写回存储（此前只改内存，进程退出即丢，下次分析读不到）
    for session in sessions:
        if session.monitor_hits:
            store.save(session)
    if events:
        notify_webhooks(events, webhook_store=webhook_store)
    rules_store.close()
    webhook_store.close()
    print(f"[monitor] 检查完成，触发事件 {len(events)} 条")
    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    """发送一条测试消息到已配置的飞书/企业微信 Webhook（FEISHU_WEBHOOK / WECHAT_WEBHOOK）。"""
    from value_agent.monitor.runner import send_webhook_text

    text = args.text or "Value Agent 测试消息 ✅"
    sent = send_webhook_text(text)
    if sent:
        print(f"[notify] 已推送 {len(sent)} 个渠道：{'、'.join(sent)}")
        return 0
    print("[notify] 未配置 FEISHU_WEBHOOK / WECHAT_WEBHOOK，或全部推送失败")
    return 1


def cmd_daily(args: argparse.Namespace) -> int:
    """每日任务：数据更新 + 监控评估 + Webhook 推送（FC 定时触发器同款逻辑）。"""
    summary = run_daily_job(
        lookback_days=getattr(args, "days", 10),
        quarterly_review=bool(getattr(args, "quarterly", False)),
    )
    updated = summary["updated"]
    print(f"[daily] 行情 +{updated.get('daily_price', 0)} / 估值 +{updated.get('valuation_history', 0)} / 跳过 {updated.get('skipped', 0)}")
    print(f"[daily] 会话 {summary['session_count']} 个 | 触发事件 {summary['monitor_events']} 条 | 推送 {summary['pushed_channels']}")
    for e in summary["events"]:
        print(f"[monitor] [{e['severity']}] {e['company_name']}({e['company_code']}) {e['message']}")
    for err in summary.get("errors", []):
        print(f"[daily] 警告：{err}")
    return 1 if summary.get("errors") else 0


def cmd_backtest(args: argparse.Namespace) -> int:
    """point-in-time 月度调仓回测（用已入库数据，无需网络）。"""
    settings = load_settings()
    storage = create_storage(settings, backend=args.backend)
    try:
        from value_agent.backtest.engine import run_backtest

        codes = load_watchlist()
        print(f"[backtest] 股票池 {len(codes)} 只 | {args.start}~{args.end} | 每月选 top {args.top} | 存储 {storage.name}")
        result = run_backtest(storage, codes, args.start, args.end, top_n=args.top)
        print(f"[backtest] 指标: {result.metrics}")
        print(f"[backtest] 净值曲线（末 3 期）: {result.equity[-3:]}")
    finally:
        storage.close()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from value_agent.main import app
    except ImportError as exc:
        raise SystemExit(f"缺少依赖，先执行 `uv sync`：{exc}") from None
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="value-agent", description="A 股价值投资 Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="分析一家公司（默认工作流）")
    p.add_argument("code", help="股票代码，如 600519")
    p.add_argument("--workflow", default="default", help="工作流 id（default 或 config/workflows 下的文件名）")
    p.add_argument("--memo", default=None, help="备忘录输出路径（可选）")
    p.add_argument("--store", choices=["memory", "sqlite", "supabase"], default="memory")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("sessions", help="列出会话")
    p.add_argument("--store", choices=["memory", "sqlite", "supabase"], default="memory")
    p.set_defaults(func=cmd_sessions)

    p = sub.add_parser("agents", help="列出已注册智能体（兼容 `agent list`）")
    p.add_argument("list", nargs="?", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_agents)

    p = sub.add_parser("workflows", help="列出可用工作流（兼容 `workflow list`）")
    p.add_argument("list", nargs="?", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_workflows)

    p = sub.add_parser("data", help="数据初始化/更新/状态/连通性自检")
    p.add_argument("action", choices=["init", "update", "status", "ping", "ddl", "validate", "snapshot", "sync", "fetch"])
    p.add_argument("--backend", choices=["sqlite", "postgres", "supabase"], default=None,
                   help="存储后端（默认按 config/settings.yaml）")
    p.add_argument("--days", type=int, default=10, help="增量更新回看天数")
    p.add_argument("code", nargs="?", help="snapshot/fetch 用：股票代码")
    p.add_argument("--as-of", default=None, help="snapshot 用：快照时点 YYYYMMDD（point-in-time）")
    p.add_argument("--from-db", default=None, help="sync 用：本地 sqlite 库路径（默认 data/market.db）")
    p.set_defaults(func=cmd_data)

    p = sub.add_parser("backtest", help="point-in-time 回测")
    p.add_argument("--start", default="20170101", help="起始 YYYYMMDD")
    p.add_argument("--end", default="20261231", help="结束 YYYYMMDD")
    p.add_argument("--top", type=int, default=5, help="每月持仓数量")
    p.add_argument("--backend", choices=["sqlite", "postgres", "supabase"], default=None)
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("monitor", help="每日监控")
    p.add_argument("--daily", action="store_true")
    p.add_argument("--quarterly", action="store_true",
                   help="9.3：财报季模式——对 warn/critical 非价格 watch 补发复查提醒")
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("notify", help="发送测试消息到飞书/企业微信 Webhook")
    p.add_argument("--text", default=None, help="测试消息内容（默认：Value Agent 测试消息 ✅）")
    p.set_defaults(func=cmd_notify)

    p = sub.add_parser("daily", help="每日任务：数据更新 + 监控 + 推送")
    p.add_argument("--days", type=int, default=10, help="增量更新回看天数")
    p.add_argument("--quarterly", action="store_true",
                   help="9.3：财报季模式——对 warn/critical 非价格 watch 补发复查提醒")
    p.set_defaults(func=cmd_daily)

    p = sub.add_parser("serve", help="启动 FastAPI 服务")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
