"""模块级评分的 PIT 组合级回测（docs/12-v2-upgrade.md §8.1 backlog）。

对比同一 PIT 月度调仓框架下的两条评分流水线：
- 基线：简化 `pit_score`（ROE/负债 + PE 分位）
- 模块：`module_pit_score`（M1 分类 → M2 财务质量引擎 + M4 估值引擎便宜度）

数据源：data/market.db（先 `value-agent data fetch <code>` 入库）。

用法：python -m scripts.backtest_module [--start 20200101] [--end 20250101] [--top-n 5]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml

from value_agent.backtest.engine import pit_score, run_backtest
from value_agent.backtest.module_score import module_pit_score
from value_agent.data.storage.sqlite_storage import SqliteMarketStorage

MARKET_DB = ROOT / "data" / "market.db"
WATCHLIST = ROOT / "config" / "watchlist.yaml"


def _load_watchlist() -> list[str]:
    raw = yaml.safe_load(WATCHLIST.read_text(encoding="utf-8")) or {}
    return [str(item["code"]) for item in raw.get("watchlist", []) if item.get("code")]


def _print_result(title: str, r) -> None:
    print(f"\n=== {title} ===")
    for k, v in r.metrics.items():
        print(f"  {k}: {v}")


def main() -> int:
    ap = argparse.ArgumentParser(description="模块级评分 PIT 回测")
    ap.add_argument("--start", default="20200101")
    ap.add_argument("--end", default="20250101")
    ap.add_argument("--top-n", type=int, default=5)
    args = ap.parse_args()

    if not MARKET_DB.exists():
        print(f"缺少行情库 {MARKET_DB}，先运行 `value-agent data fetch <code>` 入库。")
        return 1
    storage = SqliteMarketStorage(str(MARKET_DB))
    codes = _load_watchlist()
    print(f"股票池：{len(codes)} 只；区间 {args.start}~{args.end}；每月 top {args.top_n}")

    try:
        base = run_backtest(storage, codes, args.start, args.end, top_n=args.top_n, score_fn=pit_score)
        module = run_backtest(storage, codes, args.start, args.end, top_n=args.top_n, score_fn=module_pit_score)
    except Exception as exc:  # noqa: BLE001
        print(f"回测失败：{type(exc).__name__}: {exc}")
        print("本地库 schema 可能过期（如缺 bvps/ncav_ps 列），请用当前 schema 重新入库：")
        print("  value-agent data fetch <code>   （或按 data/schema.sql 迁移）")
        return 1

    _print_result("基线（简化 pit_score）", base)
    _print_result("模块引擎（module_pit_score：M1→M2→M4）", module)

    diff = (module.metrics.get("超额(策略-基准)", 0.0)
            - base.metrics.get("超额(策略-基准)", 0.0))
    print(f"\n模块流水线超额 − 基线超额 = {diff:+.2%}（年化）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
