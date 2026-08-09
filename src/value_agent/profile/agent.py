"""M0 投资者画像智能体（docs/13-investor-profile-agent.md）。

- 无依赖、确定性规则为主；只读 session.investor_profile（创建会话时附加的快照，已剥离 PII）。
- 可选智能体：**不进默认标准分析流**，由用户在自定义工作流里自选添加；
  M1/M8/M9/M10 通过 ctx.inputs.get("M0_investor_profile") 探测消费，不在流中 → 中性兜底。
- 空画像 → 中性降级（meta.degraded=True），行为与现状完全一致。
"""
from __future__ import annotations

from value_agent.agents.base import Agent, AgentContext, AgentManifest, AgentSpec
from value_agent.core.contracts import ReasonCode, build_meta
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import (
    CAPITAL_LABELS,
    DIM_LABELS,
    EDUCATION_LABELS,
    MAJOR_LABELS,
    REQUIRED_DIMS,
    RISK_LABELS,
    STYLE_LABELS,
    derive_injection_params,
    score_competence,
)
from .models import InvestorProfile, parse_investor_profile


def _persona_summary(profile: InvestorProfile) -> str:
    """一句话画像（粗粒度标签拼接，无 PII）。"""
    parts: list[str] = []
    if profile.education_level:
        parts.append(EDUCATION_LABELS.get(profile.education_level, profile.education_level))
        if profile.education_major:
            parts.append(MAJOR_LABELS.get(profile.education_major, profile.education_major))
    if profile.investment_style:
        parts.append(STYLE_LABELS.get(profile.investment_style, profile.investment_style) + "型")
    if profile.risk_tolerance:
        parts.append(RISK_LABELS.get(profile.risk_tolerance, profile.risk_tolerance) + "风险承受")
    if profile.capital_availability:
        parts.append(CAPITAL_LABELS.get(profile.capital_availability, profile.capital_availability))
    if profile.circle_of_competence:
        parts.append("能力圈:" + "、".join(DIM_LABELS.get(c, c) for c in profile.circle_of_competence[:3]))
    return " · ".join(parts) if parts else "（未填写画像）"


# 输出自描述（docs/13 §12 试点）：静态、一份；引导 M1/M8/M9/M10 与 LLM 消费 M0 输出
_M0_MANIFEST = AgentManifest(
    agent="M0_investor_profile",
    summary="投资者画像：按学历/投资风格/能力圈给出个人可理解性评级，并提供安全边际/风险/仓位个性化注入参数",
    output_fields={
        "competence.dimensions": "各能力维度胜任分 0-100 与等级 in_circle|edge|out_circle",
        "handoff.competence_level": "个人综合可理解性 high|medium|low（None=中性）",
        "handoff.required_discount_adjustment": "M8 要求折扣增量（0-0.2，比例）",
        "handoff.risk_amplification": "{tone: cautious|neutral|aggressive, flags: [个人风险提示]}",
        "handoff.position_cap": "M10 个人仓位上限（None=不限制）",
        "handoff.profile_used": "实际消费的画像字段清单（审计）",
    },
    how_to_consume=(
        "M1 读 competence.dimensions 按生意类型算个人可理解性；"
        "M8 读 handoff.required_discount_adjustment 叠加到要求折扣；"
        "M9 读 handoff.risk_amplification 展示个人风险提示；"
        "M10 读 handoff.position_cap 收窄仓位。所有字段缺失/None 时按中性处理。"
    ),
)


class M0InvestorProfileAgent(Agent):
    spec = AgentSpec(
        id="M0_investor_profile",
        name="投资者画像智能体",
        description=(
            "学历/投资风格/能力圈 → 个人可理解性评级 + 安全边际/风险注入参数"
            "（可选：加入自定义工作流即生效，默认流不包含）"
        ),
        inputs=[],
        requires_llm=False,
        version="0.1.0",
        manifest=_M0_MANIFEST,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        raw = getattr(ctx.session, "investor_profile", None)
        profile = parse_investor_profile(raw)
        if not profile.filled():
            # 空画像 → 中性降级：不放大不缩小，M1/M8/M9/M10 走现状逻辑
            return ModuleResult(
                module=self.spec.id,
                status=ModuleStatus.DONE,
                score=0.0,
                outputs={
                    "summary": _M0_MANIFEST.summary,
                    "persona_summary": "（未填写投资者画像，中性处理）",
                    "competence": {"dimensions": {}, "matched_circle": [], "overall_level": None},
                    "business_type": None,
                    "handoff": {
                        "competence_level": None,
                        "required_discount_adjustment": 0.0,
                        "discount_reasons": [],
                        "risk_amplification": {"tone": "neutral", "flags": []},
                        "position_cap": None,
                        "profile_used": [],
                    },
                },
                evidence=["投资者画像为空，M0 中性处理（不影响 M1/M8/M9/M10 默认逻辑）"],
                meta=build_meta(0.0, "low", degraded=True,
                                reason_codes=[ReasonCode.INPUT_MISSING.value]),
            )

        # 公司侧生意类型（规则层）：决定「这家公司需要哪些能力维度」。
        # M0 无依赖、可放在工作流任意位置，故自行用规则分类；M1 仍是 business_type 的最终权威。
        business_type: str | None = None
        company_name = ctx.session.company_name or ctx.session.company_code
        if ctx.data is not None:
            try:
                info = ctx.data.company_info(ctx.session.company_code)
                fin = ctx.data.financials(ctx.session.company_code)
                from value_agent.business_model.engine import analyze_business_model

                business_type = analyze_business_model(info, fin).business_type
            except Exception:  # noqa: BLE001 数据缺失 → 无公司维度（只出个人侧参数）
                business_type = None

        competence = score_competence(profile)
        params = derive_injection_params(profile, competence, business_type)

        evidence = [f"个人画像：{_persona_summary(profile)}"]
        if business_type:
            required = REQUIRED_DIMS.get(business_type, ())
            dims = competence["dimensions"]
            summary = "；".join(
                f"{DIM_LABELS.get(d, d)}={dims[d]['level']}（{dims[d]['score']} 分）"
                for d in required
            )
            evidence.append(
                f"能力圈匹配（{company_name}，生意类型 {business_type}）：{summary}"
            )
        if params["required_discount_adjustment"]:
            evidence.append(
                "安全边际注入：要求折扣 +"
                f"{params['required_discount_adjustment']:.2f}"
                f"（{'、'.join(params['discount_reasons']) or '个人画像'}）"
            )
        if params["risk_amplification"]["flags"]:
            evidence.append("个人风险提示：" + "；".join(params["risk_amplification"]["flags"]))

        outputs = {
            "summary": _M0_MANIFEST.summary,
            "persona_summary": _persona_summary(profile),
            "competence": {
                "dimensions": competence["dimensions"],
                "matched_circle": competence["matched_circle"],
                "overall_level": params["competence_level"],
            },
            "business_type": business_type,
            # 下游契约（M1/M8/M9/M10 消费；M0 不在流中时这些模块自动回退现状）
            "handoff": {
                "competence_level": params["competence_level"],
                "required_discount_adjustment": params["required_discount_adjustment"],
                "discount_reasons": params["discount_reasons"],
                "risk_amplification": params["risk_amplification"],
                "position_cap": params["position_cap"],
                "profile_used": params["profile_used"],
            },
        }
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=round(min(100.0, 40.0 + 10.0 * len(params["profile_used"])), 1),
            outputs=outputs,
            evidence=evidence,
            meta=build_meta(0.9, "high", degraded=False, reason_codes=[]),
        )
