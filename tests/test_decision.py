"""M10 决策引擎单元测试：五维加权 / 档位边界 / 一票否决。"""
import pytest

from value_agent.decision.engine import run_decision
from value_agent.sessions.models import ModuleResult, ModuleStatus


def _results(scores: dict[str, float], veto: list[str] | None = None) -> dict[str, ModuleResult]:
    res = {}
    for agent_id, score in scores.items():
        res[agent_id] = ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score)
    if veto is not None:
        res["M9_risk"] = ModuleResult(
            module="M9_risk", status=ModuleStatus.DONE, score=50, outputs={"veto": veto}
        )
    return res


def test_all_stub_neutral_around_50():
    # 全部模块 50 分 → 加权总分约 50，落入"中性/观察"
    r = run_decision(_results({f"M{i}": 50.0 for i in range(1, 12)}))
    assert r.total == pytest.approx(50.0, abs=0.1)
    assert "中性" in r.conclusion


def test_excellent_scores_hit_strong_band():
    r = run_decision(_results({f"M{i}": 90.0 for i in range(1, 12)}))
    assert r.total >= 80
    assert "强烈关注" in r.conclusion
    assert r.position == 0.10


def test_poor_scores_avoid():
    r = run_decision(_results({f"M{i}": 20.0 for i in range(1, 12)}))
    assert r.total < 50
    assert r.conclusion == "回避"
    assert r.position == 0.0


def test_veto_forces_avoid():
    r = run_decision(_results({f"M{i}": 90.0 for i in range(1, 12)}, veto=["fraud_signal_hit"]))
    assert r.conclusion == "回避（触发一票否决）"
    assert r.position == 0.0
    assert r.vetoed == ["fraud_signal_hit"]


def test_dimension_weights_applied():
    # M2=100、M4/M8=100、其余 0 → 财务(20%) + 估值(25%) 贡献
    scores = {f"M{i}": 0.0 for i in range(1, 12)}
    scores["M2_financial_quality"] = 100.0
    scores["M4_valuation"] = 100.0
    scores["M8_safety_margin"] = 100.0
    r = run_decision(scores)
    assert r.dimensions["financial_quality"] == 100.0
    assert r.dimensions["valuation_margin"] == pytest.approx(100.0)
    assert r.total == pytest.approx(45.0, abs=0.1)  # 20% + 25%
