"""画像 planner 稳定性验证（docs/12-v2-upgrade.md §9 P4 验收）。

对同一公司重复运行 M1（含画像 LLM 调用）N 次，统计 business_type / financial_subtype
的 plan 一致率（众数占比，planner.validator.stability_rate）。
验收：business_type 一致率 ≥ threshold（默认 0.8）。

用法：python -m scripts.planner_stability 600519 [--runs 5] [--threshold 0.8]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import value_agent.agents  # noqa: F401  先加载 agents（builtin→M1 链），避免循环导入
from value_agent.agents.base import AgentContext
from value_agent.business_model.agent import M1BusinessModelAgent
from value_agent.core.llm import get_llm
from value_agent.data.manager import DataManager
from value_agent.planner.validator import stability_rate
from value_agent.sessions.models import Session, SessionStatus


def run_planner(code: str, runs: int) -> tuple[list[str], list[str]]:
    """对同一公司跑 N 次 M1（temperature=0 由 LLM 配置决定），返回 business_type / financial_subtype 序列。"""
    llm = get_llm()
    if llm is None:
        print("未配置 LLM（LLM_API_KEY），画像 planner 需要 LLM。")
        return [], []
    data = DataManager()
    agent = M1BusinessModelAgent()
    business_types: list[str] = []
    financial_subtypes: list[str] = []
    for i in range(runs):
        session = Session(id=f"stab_{code}_{i}", company_code=code, status=SessionStatus.CREATED)
        ctx = AgentContext(session=session, assumptions={}, inputs={}, data=data, llm=llm)
        res = agent.run(ctx)
        plan = (res.outputs.get("handoff") or {}).get("plan_trace") or {}
        adopted = plan.get("adopted_business_type") or res.outputs.get("business_type")
        if adopted:
            business_types.append(str(adopted))
        fs = (res.outputs.get("handoff") or {}).get("financial_subtype")
        if fs:
            financial_subtypes.append(str(fs))
    return business_types, financial_subtypes


def main() -> int:
    ap = argparse.ArgumentParser(description="画像 planner 稳定性验证")
    ap.add_argument("code", help="公司代码（如 600519）")
    ap.add_argument("--runs", type=int, default=5, help="重复次数（默认 5）")
    ap.add_argument("--threshold", type=float, default=0.8, help="business_type 一致率阈值（默认 0.8）")
    args = ap.parse_args()

    bts, fss = run_planner(args.code, args.runs)
    if not bts:
        return 1
    bt_rate = stability_rate(bts)
    fs_rate = stability_rate(fss) if fss else None
    print(f"公司 {args.code} × {len(bts)} 次")
    print(f"business_type 分布：{sorted(set(bts))}")
    print(f"business_type 一致率：{bt_rate:.0%}（阈值 {args.threshold:.0%}）")
    if fs_rate is not None:
        print(f"financial_subtype 一致率：{fs_rate:.0%}")
    ok = bt_rate >= args.threshold
    print("✅ plan 稳定" if ok else "⚠️ plan 不稳定（建议降 confidence 或回退规则路由）")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
