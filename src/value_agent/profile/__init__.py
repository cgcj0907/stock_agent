"""投资者画像（M0，docs/13-investor-profile-agent.md）：个人画像 → 能力圈匹配 + 注入参数。"""
from __future__ import annotations

from .agent import M0InvestorProfileAgent
from .engine import (
    REQUIRED_DIMS,
    derive_injection_params,
    format_profile_for_llm,
    score_competence,
)
from .models import (
    CIRCLE_DIMENSIONS,
    PII_FIELDS,
    InvestorProfile,
    parse_investor_profile,
    strip_pii,
)

__all__ = [
    "CIRCLE_DIMENSIONS",
    "PII_FIELDS",
    "REQUIRED_DIMS",
    "InvestorProfile",
    "M0InvestorProfileAgent",
    "derive_injection_params",
    "format_profile_for_llm",
    "parse_investor_profile",
    "score_competence",
    "strip_pii",
]
