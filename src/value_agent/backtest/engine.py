"""回测引擎：point-in-time 月度调仓的价值策略回测（docs/01-design.md §9.1）。

- PIT：每期只用 as_of 之前的数据（storage.records_before），严格防前视
- 策略：简化价值评分（质量 ROE/负债 + 估值 PE 分位便宜度）→ 每月选 top_n
- 指标：年化收益 / 最大回撤 / 夏普 / 胜率 / 相对基准超额
- ⚠️ 简化：财报按 period 日期视为可用（未建模披露延迟），真实 PIT 需 pubDate
"""
from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass, field

from value_agent.data.snapshots import create_snapshot
from value_agent.data.storage.base import MarketStorage


@dataclass
class BacktestResult:
    equity: list[tuple[str, float]]      # (YYYYMM, 净值)
    monthly_returns: list[float]
    benchmark_returns: list[float]
    metrics: dict
    trades: list[dict] = field(default_factory=list)


def pit_score(snapshot: dict) -> float:
    """简化价值评分（0-100）：质量(年度ROE/负债) + 估值便宜度(PE分位)。"""
    fin = snapshot["tables"]["financials"]
    annual = sorted(
        (r for r in fin if str(r.get("period", "")).endswith("1231")),
        key=lambda r: str(r.get("period", "")), reverse=True,
    )
    score = 50.0
    if annual:
        r = annual[0]
        roe = r.get("roe")
        debt = r.get("debt_to_assets")
        if roe is not None:
            score += 20 if roe >= 15 else 10 if roe >= 10 else 0
        if debt is not None:
            score += 10 if debt <= 0.4 else 5 if debt <= 0.6 else 0

    val = sorted(
        (r for r in snapshot["tables"]["valuation_history"] if r.get("pe_ttm")),
        key=lambda r: str(r.get("trade_date", "")), reverse=True,
    )
    if val:
        latest = val[0]["pe_ttm"]
        history = [r["pe_ttm"] for r in val]
        pct = sum(1.0 for v in history if v <= latest) / len(history)
        score += 15 if pct < 0.2 else 10 if pct < 0.4 else 5 if pct < 0.6 else 0
    return round(min(score, 100.0), 1)


def _months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[4:6])
    end_y, end_m = int(end[:4]), int(end[4:6])
    months = []
    while (y, m) <= (end_y, end_m):
        months.append(f"{y:04d}{m:02d}")
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return months


def _close_on_or_before(storage: MarketStorage, code: str, as_of: str) -> float | None:
    recs = storage.records_before("daily_price", code, as_of)
    if not recs:
        return None
    latest = max(recs, key=lambda r: str(r.get("trade_date", "")))
    return latest.get("close")


def run_backtest(
    storage: MarketStorage,
    codes: list[str],
    start: str,
    end: str,
    top_n: int = 5,
    score_fn: Callable[[dict], float] = pit_score,
) -> BacktestResult:
    """每月：PIT 评分选 top_n → 等权持有一个月 → 统计净值与指标。

    score_fn：快照 → 0-100 分（默认简化 pit_score；可传 module_pit_score 等模块级评分，
    见 docs/12-v2-upgrade.md §8.1 backlog——模块评分的 PIT 组合级回测）。
    """
    months = _months(start, end)
    equity, bench_equity, curve, monthly, bench, trades = 1.0, 1.0, [], [], [], []

    for month in months:
        as_of = f"{month}01"
        sell_as_of = f"{_next_month(month)}01"

        scored = []
        for code in codes:
            snap = create_snapshot(storage, code, as_of=as_of)
            if not snap["tables"]["financials"]:
                continue
            scored.append((code, score_fn(snap)))
        scored.sort(key=lambda x: -x[1])
        picks = [c for c, _ in scored[:top_n]]

        # 收益：下月 01 前最后收盘 / 本月 01 前最后收盘 - 1（等权）
        rets, bench_rets = [], []
        for code in codes:
            buy = _close_on_or_before(storage, code, as_of)
            sell = _close_on_or_before(storage, code, sell_as_of)
            if buy and sell and buy > 0:
                bench_rets.append(sell / buy - 1)
                if code in picks:
                    rets.append(sell / buy - 1)

        if rets:
            port = sum(rets) / len(rets)
            bench_ret = sum(bench_rets) / len(bench_rets) if bench_rets else 0.0
            equity *= 1 + port
            bench_equity *= 1 + bench_ret
            monthly.append(port)
            curve.append((month, round(equity, 4)))
            bench.append(bench_ret)
            trades.append({"month": month, "picks": picks, "return": round(port, 4)})

    metrics = _metrics(equity, bench_equity, monthly, bench)
    return BacktestResult(
        equity=[("start", 1.0)] + curve,
        monthly_returns=monthly,
        benchmark_returns=bench,
        metrics=metrics,
        trades=trades,
    )


def _next_month(month: str) -> str:
    y, m = int(month[:4]), int(month[4:6])
    m += 1
    if m == 13:
        m, y = 1, y + 1
    return f"{y:04d}{m:02d}"


def _metrics(equity: float, bench_equity: float, monthly: list[float], bench: list[float]) -> dict:
    """指标：策略与基准都用几何复合年化（口径一致），超额 = 策略年化 − 基准年化。"""
    n = len(monthly)
    if n == 0:
        return {"总收益": 0.0, "年化收益": 0.0, "最大回撤": 0.0, "夏普": 0.0, "胜率": 0.0, "超额": 0.0}
    total = equity - 1
    annualized = (1 + total) ** (12 / n) - 1 if total > -1 else -1.0
    bench_total = bench_equity - 1
    bench_ann = (1 + bench_total) ** (12 / n) - 1 if bench_total > -1 else -1.0
    peak, max_dd = 1.0, 0.0
    eq = 1.0
    for r in monthly:
        eq *= 1 + r
        peak = max(peak, eq)
        max_dd = min(max_dd, eq / peak - 1)
    std = statistics.pstdev(monthly)
    sharpe = (statistics.mean(monthly) / std * (12 ** 0.5)) if std > 0 else 0.0
    win = sum(1 for r in monthly if r > 0) / n
    return {
        "总收益": round(total, 4),
        "年化收益": round(annualized, 4),
        "最大回撤": round(max_dd, 4),
        "夏普": round(sharpe, 2),
        "胜率": round(win, 3),
        "基准年化": round(bench_ann, 4),
        "超额(策略-基准)": round(annualized - bench_ann, 4),
    }
