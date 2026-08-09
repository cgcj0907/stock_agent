"""投资者画像评分引擎（M0，docs/13-investor-profile-agent.md §4）。

确定性规则：
- 个人胜任分 = 学历基础分 + 专业加成 + 自报能力圈加成 + 风格加成 + 职涯加成（夹逼 0-100）
- 生意类型 → 所需能力维度；维度等级 → 个人综合可理解性
- 注入参数（要求折扣增量 / 个人风险提示 / 仓位上限）全部派生自画像，不进 LLM 决策
"""
from __future__ import annotations

import logging
from pathlib import Path

from value_agent.business_model.engine import TYPE_LABEL

from .models import (
    CIRCLE_DIMENSIONS,
    InvestorProfile,
)

logger = logging.getLogger(__name__)

# ---- 默认参数（config/profile_scoring.yaml 唯一事实来源，代码兜底）----
_DEFAULTS = {
    "education_base": {
        "high_school": 40.0, "associate": 50.0, "bachelor": 60.0,
        "master": 75.0, "doctor": 85.0, "other": 50.0, "default": 55.0,
    },
    "education_major_bonus": {
        "economics": {"finance": 15.0, "default": 10.0},
        "science_engineering": {"technology": 10.0, "manufacturing": 10.0},
        "law": {"finance": 10.0},
        "medicine": {"healthcare": 15.0},
        "humanities": {"consumer": 5.0},
        "arts": {"consumer": 5.0},
    },
    "circle_bonus": 20.0,
    "style_bonus": {
        "value": {"consumer": 5.0, "finance": 5.0},
        "growth": {"technology": 5.0, "internet": 5.0},
        "dividend": {"utilities": 10.0, "energy": 5.0},
        "balanced": {},
        "contrarian": {"manufacturing": 5.0, "energy": 5.0, "real_estate": 5.0},
        "event_driven": {"finance": 5.0},
    },
    "career_bonus": {"senior": 5.0, "retired": 5.0, "mid_career": 3.0},
    "level_thresholds": {"in_circle": 70.0, "edge": 50.0},
    # 注入参数
    "discount_adjustment": {
        "competence_low": 0.08, "competence_medium": 0.03,
        "risk_tolerance_low": 0.05, "capital_short": 0.05,
        "decision_margin_of_safety": 0.03,
    },
    "position_cap": {
        "enabled": False,           # M10 个人仓位上限默认关闭（保持回测口径）
        "risk_tolerance_low": 0.10,
        "holding_short": 0.05,
        "capital_short": 0.05,
    },
}

# 生意类型 → 所需能力维度（M1 business_type，docs/13 §4.1）
REQUIRED_DIMS: dict[str, tuple[str, ...]] = {
    "consumer_monopoly": ("consumer",),
    "growth": ("technology", "healthcare", "internet"),
    "cyclical": ("manufacturing", "energy", "real_estate"),
    "financial": ("finance",),
    "asset_based": ("real_estate", "manufacturing"),
    "stable_dividend": ("utilities",),
}

DIM_LABELS: dict[str, str] = {
    "consumer": "消费", "finance": "金融", "technology": "科技",
    "healthcare": "医药医疗", "manufacturing": "制造业", "energy": "能源材料",
    "internet": "互联网平台", "utilities": "公用事业", "real_estate": "地产链",
    "overseas": "海外市场",
}

EDUCATION_LABELS = {
    "high_school": "高中及以下", "associate": "专科", "bachelor": "本科",
    "master": "硕士", "doctor": "博士", "other": "其他",
}
MAJOR_LABELS = {
    "science_engineering": "理工科", "economics": "经管金融", "law": "法律",
    "medicine": "医学", "humanities": "文史哲", "arts": "艺术设计", "other": "其他",
}
STYLE_LABELS = {
    "value": "价值", "growth": "成长", "dividend": "红利",
    "balanced": "均衡", "contrarian": "逆向", "event_driven": "事件驱动",
}
RISK_LABELS = {"low": "低", "medium": "中", "high": "高"}
HOLDING_LABELS = {"short_term": "短期", "mid_term": "中期", "long_term": "长期"}
CAPITAL_LABELS = {"long_term_idle": "长期闲钱", "mid_term_idle": "阶段性闲钱", "may_need_1_3y": "1-3 年可能要用"}
INCOME_DEP_LABELS = {"low": "低", "medium": "中", "high": "高"}


def _load_config() -> dict:
    """读 config/profile_scoring.yaml；失败返回默认参数（代码兜底）。"""
    for path in (Path("config/profile_scoring.yaml"),
                 Path(__file__).resolve().parents[3] / "config" / "profile_scoring.yaml"):
        if not path.exists():
            continue
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            merged = {k: v for k, v in _DEFAULTS.items()}
            for section in ("education_base", "education_major_bonus", "style_bonus",
                            "career_bonus", "level_thresholds", "discount_adjustment",
                            "position_cap"):
                if isinstance(raw.get(section), dict):
                    merged[section] = {**merged.get(section, {}), **raw[section]}
            return merged
        except Exception as exc:  # noqa: BLE001
            logger.warning("profile_scoring.yaml 读取失败：%s", type(exc).__name__)
            continue
    return dict(_DEFAULTS)


def _num(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def score_competence(profile: InvestorProfile) -> dict:
    """各能力维度个人胜任分（0-100）+ 等级 + 理由；公司无关。

    返回 {"dimensions": {dim: {"score", "level", "reasons"}}, "matched_circle": [...]}
    """
    cfg = _load_config()
    base_map = {**cfg.get("education_base", {}), "default": cfg["education_base"].get("default", 55.0)}
    major_bonus = cfg.get("education_major_bonus", {}) or {}
    circle_bonus = _num(cfg.get("circle_bonus", 20.0), 20.0)
    style_bonus = cfg.get("style_bonus", {}) or {}
    career_bonus = cfg.get("career_bonus", {}) or {}
    thresholds = cfg.get("level_thresholds", {})
    in_thr = _num(thresholds.get("in_circle", 70.0), 70.0)
    edge_thr = _num(thresholds.get("edge", 50.0), 50.0)

    base = _num(base_map.get(profile.education_level or ""), _num(base_map.get("default"), 55.0))
    majors = major_bonus.get(profile.education_major or "") if profile.education_major else None
    styles = style_bonus.get(profile.investment_style or "") if profile.investment_style else None
    career = _num(career_bonus.get(profile.career_stage or ""), 0.0)
    circles = set(profile.circle_of_competence)

    dimensions: dict[str, dict] = {}
    for dim in CIRCLE_DIMENSIONS:
        reasons: list[str] = []
        score = base
        reasons.append(f"学历基础 {score:.0f}")
        if majors:
            bonus = majors.get(dim) or majors.get("default", 0.0)
            if bonus:
                score += _num(bonus, 0.0)
                reasons.append(f"专业加成 +{bonus:.0f}")
        if dim in circles:
            score += circle_bonus
            reasons.append(f"自报能力圈 +{circle_bonus:.0f}")
        if styles:
            bonus = styles.get(dim, 0.0)
            if bonus:
                score += _num(bonus, 0.0)
                reasons.append(f"风格加成 +{bonus:.0f}")
        if career:
            score += career
            reasons.append(f"职涯加成 +{career:.0f}")
        score = round(min(100.0, max(0.0, score)), 1)
        level = "in_circle" if score >= in_thr else ("edge" if score >= edge_thr else "out_circle")
        dimensions[dim] = {"score": score, "level": level, "reasons": reasons}

    return {
        "dimensions": dimensions,
        "matched_circle": [c for c in CIRCLE_DIMENSIONS if c in circles],
    }


def overall_level(competence: dict, business_type: str | None) -> str | None:
    """公司相关综合可理解性：所需维度全 in_circle → high；任一 out_circle → low；否则 medium。

    business_type 未知（数据缺失/中性）→ None；所需维度在画像中缺失（如 M0 降级）→ None，
    均表示"数据不足"，调用方回退公司侧判断（不降级也不升级）。
    """
    if not business_type or business_type not in REQUIRED_DIMS:
        return None
    dims = competence.get("dimensions") or {}
    required = REQUIRED_DIMS[business_type]
    if not required:
        return None
    if any(not isinstance(dims.get(d), dict) for d in required):
        return None  # 维度数据缺失 → 中性兜底
    if any(dims[d].get("level") == "out_circle" for d in required):
        return "low"
    if all(dims[d].get("level") == "in_circle" for d in required):
        return "high"
    return "medium"


def derive_injection_params(
    profile: InvestorProfile,
    competence: dict,
    business_type: str | None,
) -> dict:
    """派生注入参数（确定性）：要求折扣增量 / 个人风险提示 / 仓位上限 / profile_used。"""
    cfg = _load_config()
    disc = cfg.get("discount_adjustment", {}) or {}
    level = overall_level(competence, business_type)

    adj = 0.0
    reasons: list[str] = []
    if level == "low":
        adj += _num(disc.get("competence_low", 0.08), 0.08)
        reasons.append(f"能力圈外（{TYPE_LABEL.get(business_type or '', business_type or '未知')}）")
    elif level == "medium":
        adj += _num(disc.get("competence_medium", 0.03), 0.03)
        reasons.append("能力圈边缘")
    if profile.risk_tolerance == "low":
        adj += _num(disc.get("risk_tolerance_low", 0.05), 0.05)
        reasons.append("低风险承受")
    if profile.capital_availability == "may_need_1_3y":
        adj += _num(disc.get("capital_short", 0.05), 0.05)
        reasons.append("资金短期可能使用")
    if profile.decision_preference == "margin_of_safety":
        adj += _num(disc.get("decision_margin_of_safety", 0.03), 0.03)
        reasons.append("偏好安全边际")
    adj = round(min(0.20, adj), 4)

    # 个人风险提示 flags（不触碰 veto 硬约束）
    flags: list[str] = []
    required = REQUIRED_DIMS.get(business_type or "", ()) if business_type else ()
    if level == "low" and required:
        out_dims = [d for d in required
                    if (competence.get("dimensions") or {}).get(d, {}).get("level") == "out_circle"]
        if out_dims:
            names = "、".join(DIM_LABELS.get(d, d) for d in out_dims)
            flags.append(f"超出投资者能力圈，难以独立评估（{names} 维度）")
    if profile.risk_tolerance == "low":
        flags.append("风险承受度低：最大回撤容忍有限，波动风险前置")
    if profile.capital_availability == "may_need_1_3y":
        flags.append("资金 1-3 年内可能使用：流动性/波动风险前置")
    if profile.income_dependency_level == "high":
        flags.append("收入对投资依赖度高：本金损失风险加重")
    if profile.holding_period == "short_term":
        flags.append("持有期短：与价值投资长期持有框架不符，事件/流动性风险前置")

    cautious = bool(level == "low" or profile.risk_tolerance == "low"
                    or profile.income_dependency_level == "high"
                    or profile.capital_availability == "may_need_1_3y"
                    or profile.holding_period == "short_term")
    tone = "cautious" if cautious else ("aggressive" if profile.risk_tolerance == "high" else "neutral")

    # 仓位上限（默认关闭，保持回测口径）
    pos_cfg = cfg.get("position_cap", {}) or {}
    position_cap: float | None = None
    if _num(pos_cfg.get("enabled", False), 0.0) > 0:
        caps = []
        if profile.risk_tolerance == "low":
            caps.append(_num(pos_cfg.get("risk_tolerance_low", 0.10), 0.10))
        if profile.holding_period == "short_term":
            caps.append(_num(pos_cfg.get("holding_short", 0.05), 0.05))
        if profile.capital_availability == "may_need_1_3y":
            caps.append(_num(pos_cfg.get("capital_short", 0.05), 0.05))
        if caps:
            position_cap = round(min(caps), 4)

    return {
        "competence_level": level,
        "required_discount_adjustment": adj,
        "discount_reasons": reasons,
        "risk_amplification": {"tone": tone, "flags": flags},
        "position_cap": position_cap,
        "profile_used": profile.filled(),
    }


def format_profile_for_llm(profile: InvestorProfile) -> str:
    """画像 → LLM 可读中文块（粗粒度标签 + 自由文本 + 资金档位；已剥离 PII）。"""
    parts: list[str] = []
    if profile.education_level:
        parts.append(f"学历={EDUCATION_LABELS.get(profile.education_level, profile.education_level)}")
    if profile.education_major:
        parts.append(f"专业={MAJOR_LABELS.get(profile.education_major, profile.education_major)}")
    if profile.career_stage:
        parts.append(f"职涯={profile.career_stage}")
    if profile.investment_style:
        parts.append(f"投资风格={STYLE_LABELS.get(profile.investment_style, profile.investment_style)}")
    if profile.risk_tolerance:
        parts.append(f"风险承受={RISK_LABELS.get(profile.risk_tolerance, profile.risk_tolerance)}")
    if profile.holding_period:
        parts.append(f"持有期={HOLDING_LABELS.get(profile.holding_period, profile.holding_period)}")
    if profile.capital_availability:
        parts.append(f"资金属性={CAPITAL_LABELS.get(profile.capital_availability, profile.capital_availability)}")
    if profile.income_dependency_level:
        parts.append(f"收入依赖={INCOME_DEP_LABELS.get(profile.income_dependency_level, profile.income_dependency_level)}")
    if profile.circle_of_competence:
        parts.append("能力圈=" + "、".join(DIM_LABELS.get(c, c) for c in profile.circle_of_competence))
    block = "；".join(parts)
    if profile.education_note:
        block += f"；教育经历补充：{profile.education_note}"
    if profile.annual_income_range or profile.investable_assets_range:
        block += f"；资金档位：年收入 {profile.annual_income_range or '未填'}，可投资资产 {profile.investable_assets_range or '未填'}"
    return block or "（投资者未填写画像）"
