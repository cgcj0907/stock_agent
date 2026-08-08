"""画像 plan 校验器（docs/12-v2-upgrade.md §4.3）：schema 校验 + LLM 主判/规则兜底。

v2.1 策略（LLM 主判，规则退化为「候选提供者 + 兜底」）：
- 画像缺失/非法（business_type 缺失或不在枚举）→ PLAN_INVALID，整体回退规则路由；
- 画像与规则一致 → 采纳画像（adopted）；
- 画像与规则冲突且 confidence=high，或 medium 且给出理由 → 采纳画像（override，记 trace）；
- 画像与规则冲突且 confidence=low，或 medium 未给理由 → business_type 回退规则
  （conflict_fallback，审慎——其余画像字段保留）。

plan_trace 落审计（P2 trace 通道），供「为什么用了这个路由」追溯；llm_vs_rule 标记
画像与规则是否一致，供 plan 稳定性监控（scripts/planner_stability.py）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.business_model.engine import normalize_business_type

from .models import (
    BUSINESS_TYPES,
    CONFIDENCE_LEVELS,
    CYCLICALITY_LEVELS,
    FINANCIAL_SUBTYPES,
    PRIMARY_METRICS,
    CompanyProfile,
)

PLAN_INVALID = "PLAN_INVALID"


@dataclass
class PlanTrace:
    """一次画像校验/路由的轨迹（进 M1 handoff.plan_trace，供审计与稳定性分析）。"""

    outcome: str  # adopted | override | conflict_fallback | fallback_rule
    reasons: list[str] = field(default_factory=list)
    adopted_business_type: str | None = None
    adopted_confidence: str = "medium"
    llm_vs_rule: str | None = None  # consistent | conflict | None（fallback_rule 无画像）

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "reasons": self.reasons,
            "adopted_business_type": self.adopted_business_type,
            "adopted_confidence": self.adopted_confidence,
            "llm_vs_rule": self.llm_vs_rule,
        }


def _enum(value, allowed: tuple[str, ...], default=None):
    if value is None:
        return default
    return value if value in allowed else default


def parse_profile(parsed: dict | None) -> CompanyProfile | None:
    """从 LLM 输出解析画像；business_type 缺失/非法 → None（整体无效，回退规则）。"""
    if not isinstance(parsed, dict):
        return None
    business_type = normalize_business_type(parsed.get("business_type"))
    if business_type is None or business_type not in BUSINESS_TYPES:
        return None
    flags = [str(f) for f in (parsed.get("special_flags") or []) if isinstance(f, str)][:6]
    return CompanyProfile(
        business_type=business_type,
        financial_subtype=_enum(parsed.get("financial_subtype"), FINANCIAL_SUBTYPES),
        cyclicality=_enum(parsed.get("cyclicality"), CYCLICALITY_LEVELS),
        primary_metric=_enum(parsed.get("primary_metric"), PRIMARY_METRICS),
        special_flags=flags,
        confidence=_enum(parsed.get("confidence"), CONFIDENCE_LEVELS, "medium"),
        notes=str(parsed.get("notes") or "")[:200],
    )


def resolve_profile(
    profile: CompanyProfile | None,
    *,
    rule_business_type: str | None,
    rule_financial_subtype: str | None,
    llm_reasons: list[str] | None = None,
) -> tuple[CompanyProfile, PlanTrace]:
    """画像 vs 规则 → (生效画像, 校验轨迹)。

    v2.1（LLM 主判，docs/12-v2-upgrade.md §4.3）：规则退化为「候选提供者 + 兜底」，
    LLM 是 business_type 的最终裁判：
    - 画像无效（缺失/非法）→ 整体回退规则（fallback_rule）
    - 画像与规则一致 → 采纳画像（adopted，llm_vs_rule=consistent）
    - 冲突且 confidence=high → 采纳画像（override，llm_vs_rule=conflict）
    - 冲突且 confidence=medium 且给出理由 → 采纳画像（override，llm_vs_rule=conflict）
    - 冲突且 confidence=low，或 medium 未给理由 → 回退规则（conflict_fallback，审慎）
    """
    if profile is None:
        effective = CompanyProfile(
            business_type=rule_business_type,
            financial_subtype=rule_financial_subtype,
            confidence="medium",
            notes="回退规则分类（画像无效）",
        )
        trace = PlanTrace(
            outcome="fallback_rule",
            reasons=[
                f"{PLAN_INVALID}：画像缺失或 business_type 非法，整体回退规则路由"
            ],
            adopted_business_type=rule_business_type,
            adopted_confidence="medium",
            llm_vs_rule=None,
        )
        return effective, trace

    if rule_business_type is not None and profile.business_type != rule_business_type:
        if profile.confidence == "low" or (
            profile.confidence == "medium" and not llm_reasons
        ):
            effective = CompanyProfile(
                business_type=rule_business_type,
                financial_subtype=profile.financial_subtype or rule_financial_subtype,
                cyclicality=profile.cyclicality,
                primary_metric=profile.primary_metric,
                special_flags=profile.special_flags,
                confidence="medium",
                notes="business_type 回退规则分类（画像冲突）",
            )
            why = (
                f"confidence={profile.confidence}"
                if profile.confidence == "low"
                else "未给出理由"
            )
            trace = PlanTrace(
                outcome="conflict_fallback",
                reasons=[
                    (
                        f"画像与规则分类冲突（{profile.business_type} vs {rule_business_type}）"
                        f"且{why}，business_type 回退规则"
                    )
                ],
                adopted_business_type=rule_business_type,
                adopted_confidence="medium",
                llm_vs_rule="conflict",
            )
            return effective, trace
        trace = PlanTrace(
            outcome="override",
            reasons=[
                (
                    f"LLM 主判与规则冲突（{rule_business_type}→{profile.business_type}），"
                    f"confidence={profile.confidence}，采纳 LLM 判断"
                )
            ],
            adopted_business_type=profile.business_type,
            adopted_confidence=profile.confidence,
            llm_vs_rule="conflict",
        )
        return profile, trace

    trace = PlanTrace(
        outcome="adopted",
        reasons=["画像与规则一致（或无规则参考），采纳画像"],
        adopted_business_type=profile.business_type,
        adopted_confidence=profile.confidence,
        llm_vs_rule="consistent",
    )
    return profile, trace


def stability_rate(values: list[str]) -> float:
    """plan 稳定性（§9 P4 验收）：众数占比 0~1；空列表 → 0。"""
    if not values:
        return 0.0
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return round(max(counts.values()) / len(values), 3)
