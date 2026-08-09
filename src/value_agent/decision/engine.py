"""M10 决策引擎：五维评分卡 + 结论档位 + 一票否决（docs/01-design.md §6）。

backlog 2026-08-07 落地：
- 8.1  LLM 总分校准幅度保护：|校准 − 规则分| > 15 → 回退规则分并记 evidence。
- 8.2  仓位联动安全边际/风险：position = 档位基准 × M8 安全边际修正 × M9 风险修正，夹逼 [0, 0.25]。
- 8.7  M9/M10 治理维度解耦：governance_risk 维度 = M6 为主，M9 只做否决/红旗标记（分数不进加权）。
- 8.9  权重/档位单一事实来源：读 config/scoring.yaml（代码保留兜底，契约测试锁一致）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from value_agent.sessions.models import ModuleResult

logger = logging.getLogger(__name__)

# 五维权重（合计 100）—— 与 config/scoring.yaml 对齐，代码内为兜底
DIMENSIONS: dict[str, dict] = {
    "business_moat":       {"modules": ["M1_business_model", "M5_moat"], "weight": 25},
    "financial_quality":   {"modules": ["M2_financial_quality"], "weight": 20},
    "growth_prosperity":   {"modules": ["M3_growth"], "weight": 20},
    "valuation_margin":    {"modules": ["M4_valuation", "M7_market", "M8_safety_margin"], "weight": 25},
    # 8.7：治理维度 = M6 为主；M9 只做否决/红旗标记（分数不再与 M6 平均，避免否决场景分数失真）
    "governance_risk":     {"modules": ["M6_governance"], "weight": 10},
}

BANDS: list[dict] = [
    {"min_score": 80, "label": "强烈关注/可建仓", "position": 0.10},
    {"min_score": 65, "label": "关注", "position": 0.05},
    {"min_score": 50, "label": "中性/观察", "position": 0.00},
    {"min_score": 0,  "label": "回避", "position": 0.00},
]

# 8.1：LLM 总分校准幅度上限（±15 分）
CALIBRATION_CAP = 15.0

# 8.2：仓位修正参数
POSITION_CLAMP = (0.0, 0.25)
_MARGIN_FACTOR = ((0.40, 1.0), (0.25, 0.9), (0.10, 0.8), (-1.0, 0.6))   # discount → 修正
_RISK_FACTOR = {"low": 1.0, "medium": 0.9, "high": 0.7, "critical": 0.5}  # max_severity → 修正

# 安全边际不足时的强制档位（关注 / 5% 观察仓，不买入）
_WATCH_BAND = next(b for b in BANDS if b["min_score"] == 65)


@dataclass
class DecisionResult:
    dimensions: dict[str, float]
    total: float
    band: dict
    position: float
    conclusion: str
    decision_code: str  # buy | watch | avoid（契约字段，§4 M10）
    blocked_by_veto: bool
    vetoed: list[str]
    evidence: list[str] = field(default_factory=list)
    decision_reasons: list[str] = field(default_factory=list)  # 契约 §4 M10：qualitative.decision_reasons
    calibration_capped: bool = False  # 8.1：LLM 校准超限回退规则分


def _load_scoring_config() -> tuple[dict | None, list[dict] | None]:
    """8.9：读 config/scoring.yaml 的 weights/bands（唯一事实来源），失败返回 (None, None) 走兜底。"""
    for path in (Path("config/scoring.yaml"),
                 Path(__file__).resolve().parents[3] / "config" / "scoring.yaml"):
        if not path.exists():
            continue
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            weights = raw.get("weights") or {}
            bands_raw = raw.get("bands") or {}
            weights = {k: float(v) for k, v in weights.items() if v is not None}
            key_map = {
                "business_moat": "moat", "financial_quality": "financial_quality",
                "growth_prosperity": "growth_prosperity", "valuation_margin": "valuation_margin",
                "governance_risk": "governance_risk",
            }
            dim_weights: dict[str, float] = {}
            for dim, key in key_map.items():
                if key in weights:
                    dim_weights[dim] = weights[key]
            bands = [
                {"min_score": float(b["min_score"]), "label": b["label"], "position": float(b["position"])}
                for b in (bands_raw.get("strong"), bands_raw.get("watch"),
                          bands_raw.get("neutral"), bands_raw.get("avoid"))
                if b and b.get("min_score") is not None
            ]
            if dim_weights and len(bands) == len(BANDS):
                return dim_weights, bands
        except Exception as exc:  # noqa: BLE001
            logger.warning("scoring.yaml 读取失败：%s", type(exc).__name__)
            continue
    return None, None


def _apply_weights() -> dict[str, dict]:
    """合并 config 权重到 DIMENSIONS（8.9），保持 modules 不变。"""
    dims = {k: dict(v) for k, v in DIMENSIONS.items()}
    cfg_weights, _ = _load_scoring_config()
    if cfg_weights:
        for k, meta in dims.items():
            if k in cfg_weights:
                meta["weight"] = cfg_weights[k]
    return dims


def apply_band(total: float, vetoed: list[str] | bool) -> tuple[dict, float, str, str]:
    """按总分 + 否决标志算出（档位, 建议仓位, 结论, 决策码）。"""
    _, bands = _load_scoring_config()
    bands = bands or BANDS
    blocked = bool(vetoed)
    band = next((b for b in bands if total >= b["min_score"]), bands[-1])
    conclusion = "回避（触发一票否决）" if blocked else band["label"]
    position = 0.0 if blocked else band["position"]
    # 决策码：否决→avoid；≥80 可建仓→buy；50~80 观察→watch；<50→avoid
    if blocked:
        decision_code = "avoid"
    elif total >= 80:
        decision_code = "buy"
    elif total >= 50:
        decision_code = "watch"
    else:
        decision_code = "avoid"
    return band, position, conclusion, decision_code


def mos_state_of(module_results: dict[str, ModuleResult]) -> str | None:
    """读 M8 handoff 的安全边际状态（attractive/fair/expensive/unavailable）。"""
    m8 = module_results.get("M8_safety_margin")
    if not m8:
        return None
    handoff = m8.outputs.get("handoff") or {}
    return handoff.get("mos_state") or m8.outputs.get("mos_state")


def apply_safety_margin_gate(
    decision_code: str,
    band: dict,
    position: float,
    conclusion: str,
    *,
    total: float,
    vetoed: list[str] | bool,
    mos_state: str | None,
) -> tuple[dict, float, str, str]:
    """M8 安全边际消费（docs/09-module-contracts.md §4 M8）：mos_state=expensive → 禁止买入。

    格雷厄姆纪律：现价高于内在价值时不追高，评分再高也只给 watch。
    必须是最终结论的唯一权威入口，agent 层不得绕过它重算结论。
    """
    if mos_state == "expensive" and not bool(vetoed) and decision_code == "buy":
        decision_code = "watch"
        band = _WATCH_BAND
        position = band["position"]
        conclusion = "关注（安全边际不足，暂不买入）"
    return band, position, conclusion, decision_code


def _margin_factor(m8: ModuleResult | None) -> float:
    """8.2：M8 安全边际修正（discount 越厚仓位越足）；无 discount 数据 → 不调整（1.0）。"""
    if m8 is None:
        return 1.0
    discount = m8.outputs.get("discount")
    if discount is None:
        return 1.0
    try:
        d = float(discount)
    except (TypeError, ValueError):
        return 1.0
    for thr, factor in _MARGIN_FACTOR:
        if d >= thr:
            return factor
    return 0.6


def _risk_factor(m9: ModuleResult | None) -> float:
    """8.2：M9 风险修正（max_severity 越高仓位越保守）；无 max_severity → 不调整（1.0）。"""
    if m9 is None:
        return 1.0
    handoff = m9.outputs.get("handoff") or {}
    sev = handoff.get("max_severity") or m9.outputs.get("max_severity")
    if sev is None:
        return 1.0
    return _RISK_FACTOR.get(sev, 1.0)


def _sized_position(
    base: float, m8: ModuleResult | None, m9: ModuleResult | None, *, vetoed: bool
) -> float:
    """8.2：仓位 = 档位基准 × M8 安全边际修正 × M9 风险修正，夹逼 [0, 0.25]。"""
    if vetoed:
        return 0.0
    low, high = POSITION_CLAMP
    pos = base * _margin_factor(m8) * _risk_factor(m9)
    return round(min(high, max(low, pos)), 4)


def run_decision(
    module_results: dict[str, ModuleResult],
    *,
    total_override: float | None = None,
    position_cap: float | None = None,
) -> DecisionResult:
    """主入口：模块评分 → 五维加权 → 结论档位 + 否决检查 + M8 安全边际门禁。

    total_override：外部（LLM 评分层）校准后的最终总分。提供时跳过规则总分，
    但一票否决 / M8 安全边际门禁等硬约束仍基于最终总分统一生效——
    防止 agent 层「按新总分重算结论」时把引擎层已施加的门禁冲掉。
    position_cap：M0 投资者画像个人仓位上限（docs/13 §5.4；None=不限制）。
    """
    dims: dict[str, float] = {}
    dims_meta = _apply_weights()
    for key, meta in dims_meta.items():
        scores = [
            module_results[m].score
            for m in meta["modules"]
            if m in module_results and module_results[m].score is not None
        ]
        dims[key] = round(sum(scores) / len(scores), 1) if scores else 0.0

    rule_total = round(
        sum(dims[k] * meta["weight"] for k, meta in dims_meta.items()) / 100.0, 1
    )
    total = round(float(total_override), 1) if total_override is not None else rule_total
    calibrated = total_override is not None and total != rule_total
    calibration_capped = False
    # 8.1：校准幅度保护——超限回退规则分
    if total_override is not None:
        delta = abs(total - rule_total)
        if delta > CALIBRATION_CAP:
            total = rule_total
            calibration_capped = True
            calibrated = False

    # 一票否决：优先读 M9 handoff.veto_flags（契约 §4 M9），经 vetoes[] 解析为 reason 展示；
    # 兼容旧 outputs.veto 直接列 id（stub 阶段为空；M9 落地后生效）。
    vetoed: list[str] = []
    m9 = module_results.get("M9_risk")
    if m9:
        handoff = m9.outputs.get("handoff") or {}
        flags = handoff.get("veto_flags")
        if flags:
            reason_by_id = {
                str(v.get("id")): str(v.get("reason") or v.get("id"))
                for v in (m9.outputs.get("vetoes") or [])
                if isinstance(v, dict) and v.get("id")
            }
            vetoed = [reason_by_id.get(str(f), str(f)) for f in flags]
        elif m9.outputs.get("veto"):
            vetoed = list(m9.outputs["veto"])
    blocked = bool(vetoed)

    band, position, conclusion, decision_code = apply_band(total, vetoed)

    # M8 安全边际门禁（唯一权威入口，agent 层必须复用，禁止绕过重算）
    m8 = module_results.get("M8_safety_margin")
    mos_state = mos_state_of(module_results)
    band, position, conclusion, decision_code = apply_safety_margin_gate(
        decision_code, band, position, conclusion,
        total=total, vetoed=vetoed, mos_state=mos_state,
    )

    # 8.2：仓位联动安全边际/风险（在档位基准 × 门禁结果之上）
    sized_position = _sized_position(position, m8, m9, vetoed=blocked)
    if sized_position != position:
        position = sized_position
    # M0 投资者画像：个人仓位上限（低风险/短期资金收窄；默认关闭）
    persona_capped = False
    if position_cap is not None and not blocked:
        cap = round(float(position_cap), 4)
        if position > cap:
            position = cap
            persona_capped = True

    decision_reasons = [
        f"五维加权总分 {total}" + (f"（规则分 {rule_total}，LLM 评分校准）" if calibrated else ""),
        f"结论档位：{conclusion}（建议仓位 {position:.0%}）",
    ]
    if calibration_capped:
        decision_reasons.append(
            f"⚠️ LLM 校准幅度超过 ±{CALIBRATION_CAP:.0f} 分，回退规则分 {rule_total}"
        )
    if mos_state == "expensive":
        decision_reasons.append(
            "M8 安全边际不足（现价高于内在价值），按格雷厄姆纪律禁止买入，降为关注"
        )
    if vetoed:
        decision_reasons.append(f"触发一票否决：{'、'.join(vetoed)}")
    if persona_capped:
        decision_reasons.append(f"个人仓位上限：{position:.0%}（M0 投资者画像：低风险/短期资金）")
    # 8.2：仓位依据说明
    if not blocked:
        factors = [
            f"M8 安全边际修正 ×{_margin_factor(m8):.2f}",
            f"M9 风险修正 ×{_risk_factor(m9):.2f}",
        ]
        decision_reasons.append(f"仓位依据：档位基准 × {' × '.join(factors)} = {position:.0%}（夹逼 [0, 25%]）")

    evidence = [
        f"五维评分：{dims}",
        f"加权总分：{total}（权重：{ {k: v['weight'] for k, v in dims_meta.items()} }）",
        f"结论档位：{conclusion}（建议仓位 {position:.0%}）",
    ]
    if calibrated:
        evidence.append(f"LLM 评分校准：规则总分 {rule_total} → 最终总分 {total}")
    if calibration_capped:
        evidence.append(
            f"⚠️ LLM 校准幅度 {delta:.1f} > ±{CALIBRATION_CAP:.0f}，回退规则分 {rule_total}（8.1 保护）"
        )
    if mos_state == "expensive":
        evidence.append(f"M8 安全边际：{mos_state}（现价高于内在价值，M10 不给出买入决策）")
    if vetoed:
        evidence.append(f"⚠️ 触发否决项：{vetoed}")
    if persona_capped:
        evidence.append(f"个人仓位上限生效：{position:.0%}（M0 投资者画像）")
    return DecisionResult(
        dimensions=dims, total=total, band=band,
        position=position, conclusion=conclusion,
        decision_code=decision_code, blocked_by_veto=blocked, vetoed=vetoed,
        evidence=evidence, decision_reasons=decision_reasons,
        calibration_capped=calibration_capped,
    )
