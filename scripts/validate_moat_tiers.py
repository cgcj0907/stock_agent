"""M5 护城河档位相关性验证（backlog 5.9）。

用 data/market.db 里的真实财报，对每只股票算 M5 规则代理档位（assess_moat），
再检验「宽/中/窄/无」档位是否与长期 ROE 水平、ROE 稳定性正相关——
这是档位定义是否合理的经验 sanity check（n 小、行业各异，仅作校准参考）。

用法：python -m scripts.validate_moat_tiers   （需本地 market.db）
"""
from __future__ import annotations

import sqlite3
import statistics
import sys
from pathlib import Path

from value_agent.backtest.calibration_ab import spearman
from value_agent.moat.engine import assess_moat

# 本地库无 industry 字段：手动映射自选股 → 行业（用于细分基准解析）
WATCHLIST_INDUSTRY = {
    "000333": ("美的集团", "家电"),
    "002415": ("海康威视", "电子"),
    "002594": ("比亚迪", "汽车"),
    "300750": ("宁德时代", "电池"),
    "600036": ("招商银行", "银行"),
    "600276": ("恒瑞医药", "医药"),
    "600519": ("贵州茅台", "白酒"),
    "600887": ("伊利股份", "乳制品"),
    "601012": ("隆基绿能", "光伏"),
    "601899": ("紫金矿业", "有色"),
}

DB = Path(__file__).resolve().parents[1] / "data" / "market.db"




def main() -> int:
    if not DB.exists():
        print(f"缺少本地库 {DB}，先运行 `value-agent data fetch <code>` 入库")
        return 1
    con = sqlite3.connect(DB)
    cur = con.cursor()

    rows_out: list[dict] = []
    for code, (name, industry) in WATCHLIST_INDUSTRY.items():
        recs = [
            {"period": r[0], "roe": r[1], "grossprofit_margin": r[2],
             "netprofit_margin": r[3], "debt_to_assets": r[4]}
            for r in cur.execute(
                "select period, roe, grossprofit_margin, netprofit_margin, debt_to_assets "
                "from financials where code=? and period like '%1231'", (code,)
            ).fetchall()
        ]
        if not recs:
            continue
        fin = {"records": recs}
        moat = assess_moat(fin, industry=industry)
        roe = [r["roe"] for r in recs if r["roe"] is not None]
        roe_mean = statistics.mean(roe) if roe else None
        roe_cv = (statistics.stdev(roe) / abs(roe_mean)) if roe and len(roe) >= 2 and roe_mean else None
        rows_out.append({
            "code": code, "name": name, "industry": industry,
            "tier": moat.rule_tier, "score": moat.score,
            "roe_mean": roe_mean, "roe_cv": roe_cv,
            "n": len(recs),
        })
    con.close()

    print(f"{'代码':<8}{'名称':<8}{'行业':<6}{'档位':<4}{'评分':>5}{'ROE均':>8}{'ROE-CV':>8}{'年数':>4}")
    for r in sorted(rows_out, key=lambda x: -x["score"]):
        print(f"{r['code']:<8}{r['name']:<8}{r['industry']:<6}{r['tier']:<4}"
              f"{r['score']:>5.0f}{r['roe_mean']:>8.1f}{r['roe_cv'] or 0:>8.2f}{r['n']:>4}")

    scores = [r["score"] for r in rows_out]
    roe_means = [r["roe_mean"] for r in rows_out if r["roe_mean"] is not None]
    roe_cvs = [r["roe_cv"] for r in rows_out if r["roe_cv"] is not None]
    print(f"\n=== 秩相关（真实数据，n={len(rows_out)}）===")
    print("M5 评分 vs 长期 ROE 均值 :", spearman(scores, roe_means))
    print("M5 评分 vs ROE 稳定性(-CV):", spearman(scores, [-c for c in roe_cvs]))

    # 档位分组统计
    by_tier: dict[str, list[float]] = {}
    for r in rows_out:
        by_tier.setdefault(r["tier"], []).append(r["roe_mean"] or 0.0)
    print("\n=== 档位 × ROE 均值 ===")
    for tier in ("宽", "中", "窄", "无"):
        vals = by_tier.get(tier)
        if vals:
            print(f"  {tier}: n={len(vals)} ROE 均值={statistics.mean(vals):.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
