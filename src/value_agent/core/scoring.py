"""LLM 评分层：让大模型按各模块评分卡给出 0-100 评分，失败回退规则分。

- 每个 agent 在规则引擎产出证据后调用 llm_score()：
  评分卡（rubric）+ 规则证据/关键事实 → LLM 输出 {"score": 0-100, "reason"}
- 未配置 LLM / llm.scoring=false / 解析失败 / 越界 → 回退 default（规则分）
- 方向统一：分越高代表该维度越有投资价值（M7 低估高分、M9 低风险高分）
"""
from __future__ import annotations

import logging
import math
from typing import Any

from value_agent.core.config import load_settings
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json

logger = logging.getLogger(__name__)

LLM_SCORE_SYSTEM = (
    "你是价值投资评分员。请以格雷厄姆、费雪、巴菲特与芒格等经典价值投资原则为尺度，"
    "对给定模块做 0-100 分评分。评分时优先看安全边际、可理解性、护城河、资本配置、"
    "现金流质量、资产负债表稳健性、增长的真实性与可持续性，以及风险是否可识别、可承受。"
    "你不是在写研报，而是在做审慎打分：不能因为措辞华丽或叙事动人而给高分，"
    "也不能仅凭单一亮点忽略结构性缺陷。若素材显示存在重大缺陷、强周期、治理疑点、"
    "高杠杆、现金流脆弱或估值缺乏保护，分数应保守。若素材不足，不得脑补缺失事实，"
    "应按信息不充分保守评分。"
    "只输出 JSON：{\"score\": 0-100 的整数, \"reason\": \"一句话理由\"}。"
    + LLM_JSON_RULE
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


def scoring_enabled() -> bool:
    """llm.scoring 开关（config/settings.yaml），默认开启。"""
    return bool(load_settings().get("llm", {}).get("scoring", True))


def parse_llm_score(value: Any, default: float | None = None) -> float | None:
    """从 LLM 输出里取 0-100 评分；缺失 / 非数字 / 越界 → default。"""
    if isinstance(value, dict):
        value = value.get("score")
    if isinstance(value, str):
        try:
            value = float(value.strip().rstrip("%"))
        except ValueError:
            return default
    if not isinstance(value, (int, float)) or math.isnan(value):  # 排除 NaN
        return default
    return max(0.0, min(100.0, float(value)))


def _fmt_facts(facts: dict) -> str:
    return "；".join(f"{k}: {v}" for k, v in facts.items() if v not in (None, "", []))


def llm_score(
    ctx,
    module_id: str,
    *,
    facts: dict,
    evidence: list[str],
    default: float,
) -> float:
    """让 LLM 给模块评分（0-100）。

    未配置 LLM / 开关关闭 / 调用失败 / 解析失败 → 返回 default（规则分），
    保证评分层是可选增强，绝不阻塞分析流程。
    """
    if getattr(ctx, "llm", None) is None or not scoring_enabled():
        return default
    rubric = SCORE_RUBRICS.get(
        module_id,
        "请按经典价值投资原则审慎评估：质量越高、安全边际越足、风险越可控，分越高。",
    )
    context = "; ".join(filter(None, [_fmt_facts(facts), "；".join(evidence or [])]))[:1500]
    prompt = (
        f"模块：{module_id}\n评分卡：{rubric}\n"
        f"分析素材（规则引擎产出）：{context or '（无素材）'}\n"
        "请只输出 JSON：{\"score\": 0-100 的整数, \"reason\": \"一句话理由\"}。"
        "score 必须是 0-100 的数字，严格依据素材与评分卡给出，不得脱离素材臆测，"
        "不要凭空编造书中观点、行业事实或公司细节。"
    )
    try:
        text = ctx.llm.chat(LLM_SCORE_SYSTEM, prompt)
        score = parse_llm_score(parse_llm_json(text))
        if score is not None:
            logger.info("[score] %s LLM 评分 %.0f（规则分 %.0f）", module_id, score, default)
            return score
        logger.warning("[score] %s LLM 评分解析失败，回退规则分 %.0f", module_id, default)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[score] %s LLM 评分失败，回退规则分 %.0f：%s", module_id, default, exc)
    return default
