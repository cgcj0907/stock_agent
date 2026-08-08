"""校准 A/B 回放（docs/12-v2-upgrade.md §8）：规则分 vs 规则+校准 v2 的区分度对比。

数据源：
- 校准轨迹语料：会话里 ModuleResult.calibration（P2：base=规则分 / final=校准后分）。
  语料源二选一：sqlite（默认，`analyze --store sqlite` 落 data/sessions.db）
  或 supabase（`--source supabase`，读 DATABASE_URL 指向的生产会话表）；
- 前向收益：data/market.db daily_price，分析日（session.created_at）后 6 个月。

⚠️ 前提：会话必须在 V2 P2（2026-08-08）之后、且开了 LLM 的分析才会带 calibration 轨迹；
旧会话（P2 前）没有 base/final 对照，会被跳过。

用法：
  python -m scripts.calibration_ab                    # 本地 sqlite 语料
  python -m scripts.calibration_ab --source supabase # 生产 Supabase 语料（需 DATABASE_URL）
  python -m scripts.calibration_ab --json            # JSON 输出（供 CI/脚本消费）
  python -m scripts.calibration_ab --collect         # 先对 watchlist 跑一轮 analyze 建语料（需数据+LLM key）

说明：
- 校准有增益 → 保持；无增益/反向 → 建议 enabled: false；平均 |delta| 偏大 → 建议收紧 cap。
- 建议只打印，不自动改 config/llm_calibration.yaml（人工确认后改）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_agent.backtest.calibration_ab import (
    FORWARD_MONTHS,
    analyze,
    extract_samples,
    forward_return,
    suggest_config,
)
from value_agent.data.storage.sqlite_storage import SqliteMarketStorage
from value_agent.sessions import SqliteStore

SESSIONS_DB = ROOT / "data" / "sessions.db"
MARKET_DB = ROOT / "data" / "market.db"
WATCHLIST = ROOT / "config" / "watchlist.yaml"


def _load_watchlist() -> list[str]:
    import yaml

    raw = yaml.safe_load(WATCHLIST.read_text(encoding="utf-8")) or {}
    return [str(item["code"]) for item in raw.get("watchlist", []) if item.get("code")]


def collect_corpus(codes: list[str]) -> None:
    """对 watchlist 跑一轮 analyze（--store sqlite）建校准语料；失败跳过并告警。"""
    print(f"[collect] 对 {len(codes)} 只股票运行 analyze（需本地数据 + LLM key；耗时较长）")
    for i, code in enumerate(codes, 1):
        print(f"[collect] {i}/{len(codes)} {code} ...")
        try:
            subprocess.run(
                [sys.executable, "-m", "value_agent", "analyze", "--store", "sqlite", code],
                cwd=ROOT, check=True, timeout=600,
            )
            print(f"[collect] {code} 完成")
        except Exception as exc:  # noqa: BLE001
            print(f"[collect] {code} 失败，跳过：{type(exc).__name__}: {exc}")
    print("[collect] 完成。重跑本脚本生成 A/B 报告。")


def main() -> int:
    ap = argparse.ArgumentParser(description="校准 A/B 回放")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--collect", action="store_true", help="先对 watchlist 建校准语料")
    ap.add_argument("--sessions-db", default=str(SESSIONS_DB), help="会话语料库（sqlite 源，默认 data/sessions.db）")
    ap.add_argument("--market-db", default=str(MARKET_DB), help="行情库（默认 data/market.db）")
    ap.add_argument("--source", choices=["sqlite", "supabase"], default="sqlite",
                    help="语料源：sqlite（本地 data/sessions.db）或 supabase（DATABASE_URL）")
    args = ap.parse_args()

    if args.collect:
        collect_corpus(_load_watchlist())
        if args.json:
            print(json.dumps({"collect": "done"}, ensure_ascii=False))
        return 0

    market_db = Path(args.market_db)
    if not market_db.exists():
        print(f"缺少行情库：{market_db}。先运行 `value-agent data fetch <code>` 入库。")
        return 1

    if args.source == "supabase":
        import os

        dsn = os.getenv("DATABASE_URL", "")
        if not dsn:
            print("--source supabase 需要 DATABASE_URL（.env 或环境变量）。")
            return 1
        try:
            from value_agent.sessions.supabase_store import SupabaseStore

            sessions = SupabaseStore(dsn).list()
        except ImportError as exc:
            print(f"缺少 psycopg2-binary：{exc}")
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"连接 Supabase 失败：{type(exc).__name__}: {exc}")
            return 1
    else:
        sessions_db = Path(args.sessions_db)
        if not sessions_db.exists():
            print(
                f"缺少语料库：{sessions_db}。\n"
                "先运行 `value-agent analyze --store sqlite <code>` 建校准语料"
                "（需要 .env 配好 LLM key），再运行本脚本。"
            )
            return 1
        sessions = SqliteStore(str(sessions_db)).list()
    samples = extract_samples(sessions)
    if not samples:
        src_hint = "（sqlite）" if args.source == "sqlite" else "（supabase）"
        print(
            f"共 {len(sessions)} 个会话{src_hint}，但未找到校准轨迹。\n"
            "说明：会话里没有 outcome 在 "
            "{applied/capped/band_protected/rejected/fallback} 的 calibration。\n"
            "可能原因：① 会话在 V2 P2（2026-08-08）之前创建（无 calibration 字段）；"
            "② 分析时未配置 LLM（trace=disabled 不入库为 A/B 样本）。\n"
            "请用带 LLM 的 `value-agent analyze --store supabase <code>`（或生产 API，"
            "SESSION_STORE=supabase）重建语料后重试。"
        )
        return 0

    storage = SqliteMarketStorage(str(market_db))
    daily_cache: dict[str, list[dict]] = {}
    for s in samples:
        if s.code not in daily_cache:
            daily_cache[s.code] = storage.records_before("daily_price", s.code)
        s.forward = forward_return(daily_cache[s.code], s.as_of, FORWARD_MONTHS)

    reports = analyze(samples)
    suggested = suggest_config(reports)

    if args.json:
        print(json.dumps({
            "sessions": len(sessions),
            "samples": len(samples),
            "with_forward_return": sum(1 for s in samples if s.forward is not None),
            "reports": {k: rep.__dict__ for k, rep in reports.items()},
            "suggested_config": suggested,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"会话数：{len(sessions)}；校准样本数：{len(samples)}；"
          f"有前向收益样本：{sum(1 for s in samples if s.forward is not None)}")
    print(f"前向收益窗口：{FORWARD_MONTHS} 个月\n")
    print(f"{'模块':<26}{'n':>4}{'规则相关':>8}{'校准相关':>8}{'增益':>7}"
          f"{'翻档率':>7}{'↑/↓':>6}{'均值Δ':>7}{'|Δ|':>6}  建议")
    for module_id, rep in reports.items():
        gain = f"{rep.corr_gain:+.2f}" if rep.corr_gain is not None else "  -  "
        rc = f"{rep.rule_corr:.2f}" if rep.rule_corr is not None else "  -  "
        cc = f"{rep.calib_corr:.2f}" if rep.calib_corr is not None else "  -  "
        print(f"{module_id:<26}{rep.n:>4}{rc:>8}{cc:>8}{gain:>7}"
              f"{rep.band_flip_rate:>7.2f}{f'{rep.up_flips}/{rep.down_flips}':>6}"
              f"{rep.mean_delta:>+7.1f}{rep.mean_abs_delta:>6.1f}  {rep.recommendation}")

    if suggested:
        print("\n=== 数据驱动建议（人工确认后改 config/llm_calibration.yaml）===")
        for module_id, change in suggested.items():
            print(f"  {module_id}: {change}")
    else:
        print("\n=== 无配置调整建议（校准增益/样本不足）===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
