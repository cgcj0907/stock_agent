"""投资者画像模型（M0，docs/13-investor-profile-agent.md §3）。

字段与 frontend/src/lib/profile.ts 枚举一一对应；解析走白名单清洗：
非法枚举值丢弃、未知键忽略、PII（身份字段）在落库/进 LLM 前剥离。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---- 枚举（与前端 profile.ts 对齐）----
EDUCATION_LEVELS = ("high_school", "associate", "bachelor", "master", "doctor", "other")
EDUCATION_MAJORS = (
    "science_engineering", "economics", "law", "medicine", "humanities", "arts", "other",
)
CAREER_STAGES = ("student", "early_career", "mid_career", "senior", "retired", "freelancer")
INVESTMENT_STYLES = ("value", "growth", "dividend", "balanced", "contrarian", "event_driven")
RISK_TOLERANCES = ("low", "medium", "high")
HOLDING_PERIODS = ("short_term", "mid_term", "long_term")
INVESTMENT_GOALS = (
    "capital_preservation", "steady_growth", "long_term_compounding", "aggressive_return",
)
LOSS_TOLERANCE_RANGES = ("loss_lt_5", "loss_5_10", "loss_10_20", "loss_20_30", "loss_gt_30")
CAPITAL_AVAILABILITIES = ("long_term_idle", "mid_term_idle", "may_need_1_3y")
INCOME_DEPENDENCY_LEVELS = ("low", "medium", "high")
DECISION_PREFERENCES = ("margin_of_safety", "growth_upside", "balanced")
ANNUAL_INCOME_RANGES = ("income_lt_20", "income_20_50", "income_50_100",
                        "income_100_300", "income_300_500", "income_gt_500")
INVESTABLE_ASSETS_RANGES = ("assets_lt_30", "assets_30_100", "assets_100_300",
                            "assets_300_1000", "assets_1000_3000", "assets_gt_3000")

# 能力维度（与前端 CIRCLE_OF_COMPETENCE_OPTIONS 对齐）
CIRCLE_DIMENSIONS = (
    "consumer", "finance", "technology", "healthcare", "manufacturing",
    "energy", "internet", "utilities", "real_estate", "overseas",
)

# 可理解性等级（与 M1 _understandability_level 枚举一致）
COMPETENCE_LEVELS = ("high", "medium", "low")
# 维度等级
DIM_LEVELS = ("in_circle", "edge", "out_circle")

# 直接身份字段：落库/进 LLM 前必须剥离（docs/13 §9）
PII_FIELDS = frozenset({
    "display_name", "email", "phone", "avatar", "avatar_path", "avatar_url",
    "user_id", "id", "created_at", "updated_at",
})

# 每个维度可保留的自报能力圈上限（前端同约束 5 个）
MAX_CIRCLE_ITEMS = 5
# 自由文本最大长度（education_note 截断，防 payload 膨胀）
MAX_NOTE_LEN = 200


def strip_pii(raw: dict | None) -> dict:
    """剔除可直接定位身份/元数据字段，返回仅含画像字段的 dict（未知键一并丢弃）。"""
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k not in PII_FIELDS}


def _enum(value, allowed: tuple[str, ...]):
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v if v in allowed else None


@dataclass
class InvestorProfile:
    """投资者画像（粗粒度标签，无 PII）。"""

    education_level: str | None = None
    education_major: str | None = None
    education_note: str = ""
    career_stage: str | None = None
    investment_style: str | None = None
    risk_tolerance: str | None = None
    holding_period: str | None = None
    investment_goal: str | None = None
    loss_tolerance_range: str | None = None
    capital_availability: str | None = None
    income_dependency_level: str | None = None
    decision_preference: str | None = None
    circle_of_competence: list[str] = field(default_factory=list)
    annual_income_range: str | None = None
    investable_assets_range: str | None = None

    def filled(self) -> list[str]:
        """非空字段名清单（审计/中性判断用）。"""
        out = []
        for key, value in self.to_dict().items():
            if isinstance(value, str):
                if value.strip():
                    out.append(key)
            elif isinstance(value, list) and value:
                out.append(key)
        return out

    def to_dict(self) -> dict:
        return {
            "education_level": self.education_level,
            "education_major": self.education_major,
            "education_note": self.education_note,
            "career_stage": self.career_stage,
            "investment_style": self.investment_style,
            "risk_tolerance": self.risk_tolerance,
            "holding_period": self.holding_period,
            "investment_goal": self.investment_goal,
            "loss_tolerance_range": self.loss_tolerance_range,
            "capital_availability": self.capital_availability,
            "income_dependency_level": self.income_dependency_level,
            "decision_preference": self.decision_preference,
            "circle_of_competence": list(self.circle_of_competence),
            "annual_income_range": self.annual_income_range,
            "investable_assets_range": self.investable_assets_range,
        }


def parse_investor_profile(raw: dict | None) -> InvestorProfile:
    """白名单清洗：非法枚举丢弃、未知键忽略；空/缺失 → 全空画像（中性）。"""
    if not isinstance(raw, dict):
        return InvestorProfile()
    circles = [
        c for c in (raw.get("circle_of_competence") or [])
        if isinstance(c, str) and c.strip() in CIRCLE_DIMENSIONS
    ][:MAX_CIRCLE_ITEMS]
    note = raw.get("education_note")
    note = str(note).strip()[:MAX_NOTE_LEN] if isinstance(note, str) else ""
    return InvestorProfile(
        education_level=_enum(raw.get("education_level"), EDUCATION_LEVELS),
        education_major=_enum(raw.get("education_major"), EDUCATION_MAJORS),
        education_note=note,
        career_stage=_enum(raw.get("career_stage"), CAREER_STAGES),
        investment_style=_enum(raw.get("investment_style"), INVESTMENT_STYLES),
        risk_tolerance=_enum(raw.get("risk_tolerance"), RISK_TOLERANCES),
        holding_period=_enum(raw.get("holding_period"), HOLDING_PERIODS),
        investment_goal=_enum(raw.get("investment_goal"), INVESTMENT_GOALS),
        loss_tolerance_range=_enum(raw.get("loss_tolerance_range"), LOSS_TOLERANCE_RANGES),
        capital_availability=_enum(raw.get("capital_availability"), CAPITAL_AVAILABILITIES),
        income_dependency_level=_enum(raw.get("income_dependency_level"), INCOME_DEPENDENCY_LEVELS),
        decision_preference=_enum(raw.get("decision_preference"), DECISION_PREFERENCES),
        circle_of_competence=circles,
        annual_income_range=_enum(raw.get("annual_income_range"), ANNUAL_INCOME_RANGES),
        investable_assets_range=_enum(raw.get("investable_assets_range"), INVESTABLE_ASSETS_RANGES),
    )
