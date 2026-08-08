"""公司画像（Company Profile）模型（docs/12-v2-upgrade.md §4.2）。

一次 LLM 调用输出结构化画像，M1（生意类型/可理解性）、M2（分行业口径）、
M4（估值方法路由）、M7（主指标）消费同一份；M3/M5 间接继承。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 枚举（与 config/valuation_routing.yaml 键 / financial_routing.yaml 对齐）
BUSINESS_TYPES = ("cyclical", "consumer_monopoly", "growth", "financial", "asset_based", "stable_dividend")
FINANCIAL_SUBTYPES = ("bank", "broker", "insurance", "real_estate", "other")
PRIMARY_METRICS = ("pe", "pb", "null")  # null = 退化为 max(PE,PB) 保守口径（M7）
CYCLICALITY_LEVELS = ("low", "medium", "high")
CONFIDENCE_LEVELS = ("high", "medium", "low")


@dataclass
class CompanyProfile:
    """LLM 画像（一次调用产出，M1/M2/M4/M7 消费同一份）。"""

    business_type: str | None = None
    financial_subtype: str | None = None
    cyclicality: str | None = None
    primary_metric: str | None = None
    special_flags: list[str] = field(default_factory=list)
    confidence: str = "medium"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "business_type": self.business_type,
            "financial_subtype": self.financial_subtype,
            "cyclicality": self.cyclicality,
            "primary_metric": self.primary_metric,
            "special_flags": self.special_flags,
            "confidence": self.confidence,
            "notes": self.notes,
        }
