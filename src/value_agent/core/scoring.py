"""LLM 评分校准层 v2：规则分锚 + LLM 有界偏移（docs/12-v2-upgrade.md §6）。

- 每个 agent 在规则引擎产出证据后调用 llm_score()：
  规则分 default + 证据 evidence → LLM 输出 {delta, reasons, evidence_refs, new_facts}
- delta 制（不再是绝对分替换）：最终分 = clamp(default + delta, 0, 100)
- 校验规则（docs/12-v2-upgrade.md §6.3）：
  1) delta 超模块上限 → 截断（CALIBRATION_CAPPED）
  2) 上限 = min(模块策略 cap, 置信度 cap)；置信度未显式给出时只用模块 cap
  3) 抬分须证据（evidence_refs / new_facts 至少其一），否则拒绝回退规则分
  4) 压分只需 ≥1 条理由（审慎原则，宁可保守）
  5) 档位边界保护：跨档且贴近阈值时需 ≥2 条 new_facts，否则封顶在档内
  6) 失败 / 未配置 LLM / 模块禁用 → 回退规则分（降级兜底）
- 无 LLM 时模块照常运行（规则分）；评分层是可选增强，绝不阻塞分析流程。
- 方向统一：分越高代表该维度越有投资价值（M7 低估高分、M9 低风险高分）
"""
from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from value_agent.core.config import load_settings
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json

logger = logging.getLogger(__name__)

LLM_SCORE_SYSTEM = (
    "你是价值投资评分复核员。请以格雷厄姆、费雪、巴菲特与芒格等经典价值投资原则为尺度，"
    "复核规则引擎给出的模块评分（0-100），只做有界小幅修正（delta）。"
    "评分时优先看安全边际、可理解性、护城河、资本配置、现金流质量、资产负债表稳健性、"
    "增长的真实性与可持续性，以及风险是否可识别、可承受。"
    "你不是在写研报，而是在做审慎打分：不能因为措辞华丽或叙事动人而给高分，"
    "也不能仅凭单一亮点忽略结构性缺陷。若素材显示存在重大缺陷、强周期、治理疑点、"
    "高杠杆、现金流脆弱或估值缺乏保护，分数应保守。若素材不足，不得脑补缺失事实，"
    "应按信息不充分保守处理，delta 从紧。"
)

# 各模块评分卡（方向统一：分越高越有投资价值）
SCORE_RUBRICS: dict[str, str] = {
    "M1_business_model": (
        "从价值投资者是否能真正看懂这门生意出发评分。商业模式越简单清晰、盈利逻辑越稳定、"
        "行业结构与竞争位置越明确、越处于能力圈内，分越高；若强依赖景气、政策、商品价格"
        "或难以验证的叙事，应保守。"
    ),
    "M2_financial_quality": (
        "重点看财务报表是否体现高质量经营。盈利能力强且稳定、现金流与利润匹配、杠杆适中、"
        "资产负债表稳健、会计迹象干净，分越高；若利润好看但现金流差、负债重、波动大或有"
        "潜在粉饰信号，分应降低。"
    ),
    "M3_growth": (
        "只奖励高质量、可持续、可兑现的增长。增长来自真实需求、竞争优势与有效再投资，且"
        "不显著牺牲回报率和现金流，分越高；若增长更多来自周期上行、低价扩张或激进假设，"
        "应谨慎。"
    ),
    "M4_valuation": (
        "按格雷厄姆式审慎原则看估值。估值方法与生意类型越匹配、关键假设越克制、数据越完整、"
        "内在价值区间越有解释力，分越高；若估值建立在脆弱假设上，或对周期股使用过度乐观的"
        "远期推演，分应偏低。"
    ),
    "M5_moat": (
        "从企业是否具备可持续竞争优势出发评分。品牌、成本、渠道、网络效应、转换成本、规模"
        "优势等护城河越清晰且越能转化为长期高回报，分越高；若优势短暂、易被复制或主要靠"
        "景气红利，分应降低。"
    ),
    "M6_governance": (
        "重点看管理层与股东是否利益一致，以及资本配置是否理性。治理规范、信息披露坦诚、"
        "分红回购审慎、并购克制、资本配置长期有纪律，分越高；若治理混乱、关联交易复杂、"
        "融资冲动或侵蚀股东回报，分应偏低。"
    ),
    "M7_market": (
        "从市场先生的报价是否提供机会出发评分。当前估值位置越低、相对历史与基本面越便宜、"
        "股债性价比越有吸引力，分越高；若市场已充分甚至过度反映乐观预期，分应降低。"
    ),
    "M8_safety_margin": (
        "安全边际越厚，分越高。买入价格相对保守内在价值折扣越深、下行保护越强、即使判断"
        "有偏差仍不易永久亏损，分越高；若几乎没有缓冲垫，应低分。"
    ),
    "M9_risk": (
        "把风险理解为永久性资本损失的可能，而不只是价格波动。风险来源越少、可识别性越强、"
        "可承受性越高，分越高；若存在高杠杆、治理疑点、商业模式脆弱、外部依赖强或尾部风险"
        "难评估，分应降低。"
    ),
    "M10_decision": (
        "按综合投资价值评分，而不是按故事吸引力评分。只有当商业质量、财务质量、估值保护、"
        "治理与风险共同支持时，才应高分；若触发一票否决、关键短板明显或结论建立在脆弱假设上，"
        "应给低分。"
    ),
    "M11_monitor": (
        "监控规则越像一个审慎投资者持续跟踪企业的清单，分越高。关键指标覆盖越完整、触发条件"
        "越清楚、能及时暴露基本面恶化或估值失衡，分越高；若规则空泛、缺少可执行阈值，分应降低。"
    ),
}

# 档位阈值（与 config/scoring.yaml bands 对齐；P2 迁移为配置读取）
BAND_THRESHOLDS: tuple[float, ...] = (80.0, 65.0, 50.0)
BAND_MARGIN = 5.0
MIN_NEW_FACTS_TO_CROSS = 2

# 置信度 → 校准上限（docs/12-v2-upgrade.md §6.3 规则 2；confidence 未显式给出时不用）
CONFIDENCE_CAP: dict[str, float] = {"high": 5.0, "medium": 10.0, "low": 15.0}

# 分模块校准策略（docs/12-v2-upgrade.md §6.4；P2 迁移到 config/llm_calibration.yaml）
CALIBRATION_POLICY: dict[str, dict] = {
    # 纯数值模块：禁用校准（LLM 只给理由，不动分）
    "M2_financial_quality": {"enabled": False, "cap": 0.0},
    "M7_market": {"enabled": False, "cap": 0.0},
    "M8_safety_margin": {"enabled": False, "cap": 0.0},
    # 语义模块：校准 ±15，抬分须证据
    "M1_business_model": {"enabled": True, "cap": 15.0},
    "M5_moat": {"enabled": True, "cap": 15.0},
    "M6_governance": {"enabled": True, "cap": 15.0},
    # M10 决策：有界校准 ±15（与 decision/engine.py CALIBRATION_CAP 双层保护一致）；
    # veto / M8 门禁等硬约束仍由决策引擎统一生效，不可让渡。
    "M10_decision": {"enabled": True, "cap": 15.0},
}
DEFAULT_CALIBRATION: dict = {"enabled": True, "cap": 10.0}


@dataclass
class CalibrationProposal:
    """LLM 输出的有界校准提议（delta 制，docs/12-v2-upgrade.md §6.2）。"""

    delta: float
    reasons: list[str] = field(default_factory=list)
    evidence_refs: list[int] = field(default_factory=list)
    new_facts: list[str] = field(default_factory=list)


@dataclass
class CalibrationTrace:
    """一次校准的完整轨迹（P2 落库 / 审计用）。"""

    module_id: str = ""
    base: float = 0.0
    final: float = 0.0
    outcome: str = "applied"  # applied | capped | rejected_no_evidence | rejected_no_reason | band_protected
    notes: list[str] = field(default_factory=list)
    proposal_delta: float | None = None
    reasons: list[str] = field(default_factory=list)
    evidence_refs: list[int] = field(default_factory=list)
    new_facts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "module_id": self.module_id,
            "base": self.base,
            "final": self.final,
            "outcome": self.outcome,
            "notes": self.notes,
            "delta": self.proposal_delta,
            "reasons": self.reasons,
            "evidence_refs": self.evidence_refs,
            "new_facts": self.new_facts,
        }


def scoring_enabled() -> bool:
    """llm.scoring 开关（config/settings.yaml），默认开启。"""
    return bool(load_settings().get("llm", {}).get("scoring", True))
def _clean_str_list(value: Any, *, max_items: int = 3, max_len: int = 80) -> list[str]:
    """清洗字符串数组：只保留非空短字符串，限制条数与长度。"""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s:
            out.append(s[:max_len])
        if len(out) >= max_items:
            break
    return out


def parse_llm_calibration(value: Any) -> CalibrationProposal | None:
    """从 LLM 输出解析校准提议；缺 delta / 非数字 / NaN → None（回退规则分）。"""
    if not isinstance(value, dict):
        return None
    delta = value.get("delta")
    if isinstance(delta, str):
        try:
            delta = float(delta.strip().rstrip("%"))
        except ValueError:
            return None
    if not isinstance(delta, (int, float)) or math.isnan(delta):
        return None
    refs: list[int] = []
    raw_refs = value.get("evidence_refs")
    if isinstance(raw_refs, list):
        for r in raw_refs:
            try:
                refs.append(int(r))
            except (TypeError, ValueError):
                continue
    return CalibrationProposal(
        delta=float(delta),
        reasons=_clean_str_list(value.get("reasons")),
        evidence_refs=refs,
        new_facts=_clean_str_list(value.get("new_facts")),
    )


def _calibration_config_candidates() -> list[Path]:
    return [
        Path("config/llm_calibration.yaml"),
        Path(__file__).resolve().parents[3] / "config" / "llm_calibration.yaml",
    ]


def load_calibration_config() -> tuple[dict | None, dict | None]:
    """读 config/llm_calibration.yaml → (policy, band_protection)；缺失/解析失败返回 (None, None)。

    policy 形如 {module_id: {"enabled", "cap", "require_evidence_for_up"}, "__default__": {...}}；
    band_protection 形如 {"margin", "min_new_facts_to_cross"}。
    """
    for path in _calibration_config_candidates():
        if not path.exists():
            continue
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            policy: dict = {}
            for mid, meta in (raw.get("calibration") or {}).items():
                if isinstance(meta, dict):
                    policy[mid] = {
                        "enabled": bool(meta.get("enabled", True)),
                        "cap": float(meta.get("cap", 10.0)),
                        "require_evidence_for_up": bool(meta.get("require_evidence_for_up", True)),
                    }
            default = raw.get("default") or {}
            policy["__default__"] = {
                "enabled": bool(default.get("enabled", True)),
                "cap": float(default.get("cap", 10.0)),
                "require_evidence_for_up": bool(default.get("require_evidence_for_up", True)),
            }
            bp = raw.get("band_protection") or {}
            band = {
                "margin": float(bp.get("margin", BAND_MARGIN)),
                "min_new_facts_to_cross": int(bp.get("min_new_facts_to_cross", MIN_NEW_FACTS_TO_CROSS)),
            }
            if policy:
                return policy, band
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_calibration.yaml 解析失败，使用代码兜底：%s", type(exc).__name__)
            break
    return None, None


def _resolve_policy(module_id: str, policy: dict | None) -> dict:
    if policy is None:
        return CALIBRATION_POLICY.get(module_id, DEFAULT_CALIBRATION)
    return policy.get(module_id, policy.get("__default__", DEFAULT_CALIBRATION))
def confidence_from_completeness(completeness: str) -> str:
    """completeness → 校准置信度（docs/12-v2-upgrade.md §6.6）。

    画像/数据完整度高 → 规则分可信，收紧校准上限（high→±5）；
    降级 → 放宽上限（low→±15），但证据要求不变（抬分仍须证据）。
    """
    return completeness if completeness in CONFIDENCE_CAP else "medium"



def _fmt_facts(facts: dict) -> str:
    return "；".join(f"{k}: {v}" for k, v in facts.items() if v not in (None, "", []))


# ---------- 校准核心（纯函数，便于单测） ----------


def _band_of(score: float, thresholds: Sequence[float]) -> int:
    """分数所在档位下标（thresholds 降序；返回第一个 score>=thr 的下标）。"""
    for i, thr in enumerate(sorted(thresholds, reverse=True)):
        if score >= thr:
            return i
    return len(thresholds)


def _crossed_boundaries(base: float, final: float, thresholds: Sequence[float]) -> list[float]:
    """base→final 跨过的档位阈值（升序）。"""
    lo, hi = (base, final) if base < final else (final, base)
    return [t for t in sorted(thresholds) if lo < t <= hi]


def _clamp_to_base_side(base: float, boundary: float) -> float:
    """把最终分拉回 base 所在档位一侧（不跨 boundary）。"""
    if base < boundary:
        return min(base, boundary - 1.0)
    return max(base, boundary)


def calibrate_score(
    base: float,
    proposal: CalibrationProposal,
    *,
    evidence: Sequence[str],
    cap: float,
    band_thresholds: Sequence[float] = BAND_THRESHOLDS,
    band_margin: float = BAND_MARGIN,
    min_new_facts_to_cross: int = MIN_NEW_FACTS_TO_CROSS,
    require_evidence_for_up: bool = True,
) -> tuple[float, CalibrationTrace]:
    """规则分 + 有界校准 → (最终分, trace)。永不直接采纳 LLM 绝对分。

    - 最终分 = clamp(base + delta, 0, 100)；
    - delta 超 cap 截断（CALIBRATION_CAPPED）；
    - 抬分须证据 / 压分须理由，否则拒绝回退规则分；
    - 跨档且贴近阈值时须足够 new_facts，否则封顶在档内。
    """
    notes: list[str] = []
    outcome = "applied"

    delta = proposal.delta
    if delta == 0:
        return base, CalibrationTrace(base=base, final=base, outcome="applied",
                                      notes=["delta=0，无调整"], proposal_delta=0.0,
                                      reasons=proposal.reasons, evidence_refs=proposal.evidence_refs,
                                      new_facts=proposal.new_facts)

    # 1) 幅度保护：超上限截断
    capped_delta = max(-cap, min(cap, delta))
    if abs(capped_delta) < abs(delta):
        outcome = "capped"
        notes.append(
            f"LLM 校准幅度 {delta:+.1f} 超过上限 ±{cap:.0f}，截断至 {capped_delta:+.1f}（CALIBRATION_CAPPED）"
        )
        delta = capped_delta

    # 2) 证据 / 理由校验：抬分须证据、压分须理由（审慎原则）
    has_evidence = bool(proposal.new_facts) or any(
        0 <= i < len(evidence) for i in proposal.evidence_refs
    )
    if delta > 0 and require_evidence_for_up and not has_evidence:
        return base, CalibrationTrace(base=base, final=base, outcome="rejected_no_evidence",
                                      notes=["抬分无证据（evidence_refs/new_facts 均为空），拒绝校准，回退规则分"],
                                      proposal_delta=proposal.delta, reasons=proposal.reasons,
                                      evidence_refs=proposal.evidence_refs, new_facts=proposal.new_facts)
    if delta < 0 and not proposal.reasons:
        return base, CalibrationTrace(base=base, final=base, outcome="rejected_no_reason",
                                      notes=["压分无理由，拒绝校准，回退规则分"],
                                      proposal_delta=proposal.delta, reasons=proposal.reasons,
                                      evidence_refs=proposal.evidence_refs, new_facts=proposal.new_facts)

    final = min(100.0, max(0.0, base + delta))

    # 3) 档位边界保护：抬分跨档且贴近阈值 → 需足够 new_facts，否则封顶在档内。
    # 压分（更保守）不加此保护——审慎原则下压分只需理由（规则 4），避免误伤保守修正。
    if final > base and _band_of(final, band_thresholds) != _band_of(base, band_thresholds):
        for boundary in _crossed_boundaries(base, final, band_thresholds):
            if abs(base - boundary) < band_margin and len(proposal.new_facts) < min_new_facts_to_cross:
                final = _clamp_to_base_side(base, boundary)
                outcome = "band_protected"
                notes.append(
                    f"档位边界保护：贴近 {boundary:.0f} 分档位阈值跨档但 new_facts 仅 "
                    f"{len(proposal.new_facts)} 条（需 ≥{min_new_facts_to_cross}），封顶在档内"
                )
                break

    return final, CalibrationTrace(base=base, final=final, outcome=outcome, notes=notes,
                                   proposal_delta=proposal.delta, reasons=proposal.reasons,
                                   evidence_refs=proposal.evidence_refs, new_facts=proposal.new_facts)


def _trace_entry(module_id: str, base: float, outcome: str, notes: list[str]) -> dict:
    """构造未校准路径的 trace（disabled / fallback），便于审计「为什么分没被校准」。"""
    return {
        "module_id": module_id,
        "base": base,
        "final": base,
        "outcome": outcome,
        "notes": notes,
        "delta": None,
        "reasons": [],
        "evidence_refs": [],
        "new_facts": [],
    }


# ---------- LLM 评分入口 ----------


def llm_score(
    ctx,
    module_id: str,
    *,
    facts: dict,
    evidence: list[str],
    default: float,
    confidence: str | None = None,
    band_thresholds: Sequence[float] = BAND_THRESHOLDS,
    trace: dict | None = None,
) -> float:
    """让 LLM 对规则分做有界校准（delta 制），返回最终分。

    未配置 LLM / 开关关闭 / 模块禁用 / 调用失败 / 解析失败 / 校验不通过
    → 返回 default（规则分），保证评分层是可选增强，绝不阻塞分析流程。

    confidence：规则层置信度（high|medium|low），用于收紧校准上限
    （docs/12-v2-upgrade.md §6.6：planner 引入降级路径 → confidence 低 → 上限放宽但证据更严）；
    未给出时只用模块策略 cap。

    trace：可选 dict，填充本次校准轨迹（P2 落库 / 审计用）。
    """
    if default is None:
        return default
    policy_cfg, band_cfg = load_calibration_config()
    if getattr(ctx, "llm", None) is None or not scoring_enabled():
        if trace is not None:
            trace.update(_trace_entry(module_id, default, "disabled", []))
        return default
    policy = _resolve_policy(module_id, policy_cfg)
    if not policy.get("enabled", True):
        if trace is not None:
            trace.update(_trace_entry(module_id, default, "disabled", []))
        return default
    cap = float(policy.get("cap", 10.0))
    if confidence is not None:
        cap = min(cap, CONFIDENCE_CAP.get(confidence, 10.0))
    require_evidence_for_up = bool(policy.get("require_evidence_for_up", True))
    band_margin = float(band_cfg["margin"]) if band_cfg else BAND_MARGIN
    min_new_facts_to_cross = (
        int(band_cfg["min_new_facts_to_cross"]) if band_cfg else MIN_NEW_FACTS_TO_CROSS
    )

    rubric = SCORE_RUBRICS.get(
        module_id,
        "请按经典价值投资原则审慎评估：质量越高、安全边际越足、风险越可控，分越高。",
    )
    context = "; ".join(filter(None, [_fmt_facts(facts), "；".join(evidence or [])]))[:1500]
    prompt = (
        f"模块：{module_id}\n评分卡：{rubric}\n"
        f"规则评分（基准，由确定性规则引擎产出）：{default}\n"
        f"分析素材（规则引擎产出）：{context or '（无素材）'}\n"
        "请判断规则评分是否合理，并给出有界修正：\n"
        "- delta：相对规则评分的偏移（最终分 = 规则评分 + delta），范围 -15~+15；合理则填 0。\n"
        "- reasons：1~3 条简短理由。\n"
        "- evidence_refs：引用的素材下标（从 0 开始）。抬分（delta>0）必须至少引用 1 条素材"
        "或提供 new_facts；压分（delta<0）至少给出 1 条理由。\n"
        "- new_facts：规则层未覆盖、你能从素材中确认的新事实（不得编造）；跨档位边界时需 ≥2 条。\n"
        "只输出 JSON：{\"delta\": 0, \"reasons\": [...], \"evidence_refs\": [...], \"new_facts\": [...]}。"
        "delta 必须是 -15~15 的整数；严格依据素材与评分卡给出，不得脱离素材臆测，"
        "不要凭空编造书中观点、行业事实或公司细节。"
        + LLM_JSON_RULE
    )
    try:
        text = ctx.llm.chat(LLM_SCORE_SYSTEM, prompt)
        proposal = parse_llm_calibration(parse_llm_json(text))
        if proposal is None:
            if trace is not None:
                trace.update(_trace_entry(module_id, default, "fallback", ["LLM 校准解析失败，回退规则分"]))
            logger.warning("[score] %s LLM 校准解析失败，回退规则分 %.0f", module_id, default)
            return default
        final, cal = calibrate_score(
            default, proposal, evidence=evidence, cap=cap, band_thresholds=band_thresholds,
            band_margin=band_margin, min_new_facts_to_cross=min_new_facts_to_cross,
            require_evidence_for_up=require_evidence_for_up,
        )
        if trace is not None:
            cal.module_id = module_id
            trace.update(cal.to_dict())
        logger.info(
            "[score] %s delta %+.0f → %.0f（规则分 %.0f，outcome=%s）",
            module_id, proposal.delta, final, default, cal.outcome,
        )
        return final
    except Exception as exc:  # noqa: BLE001
        if trace is not None:
            trace.update(_trace_entry(module_id, default, "fallback",
                                      [f"LLM 校准调用失败，回退规则分：{type(exc).__name__}"]))
        logger.warning("[score] %s LLM 校准失败，回退规则分 %.0f：%s", module_id, default, exc)
        return default
