"""M6 治理与资本配置智能体：分红代理评分 + 治理事件 + LLM 定性两层合成。

修复点（相对旧版，对齐 docs/09-module-contracts.md §4 M6）：
1. 规则层 = 分红代理 + 可选治理事件（质押/减持/回购/监管/审计），事件映射为结构化风险码；
2. LLM 定性 schema 对齐契约字段（shareholder_alignment / capital_allocation /
   governance_risks[] / disclosure_quality），合法 governance_risks 真正回填
   handoff.governance_risk_codes（M9 消费），不再只塞 llm_qualitative；
3. handoff.governance_score = 最终分数（含 LLM 评分校准），M4/M9/M10 读同一个数，
   避免「外层 score 与 handoff 分数口径漂移」。
"""
from __future__ import annotations

import logging

from value_agent.agents.base import Agent, AgentContext, AgentSpec, degraded_module_result
from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json
from value_agent.core.scoring import llm_score
from value_agent.data.references import CompanyReferences, format_reference_list, select_references
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_governance

logger = logging.getLogger(__name__)

# 治理风险码白名单（LLM 输出必须落在这些码内，防幻觉字段污染下游；M9 消费）
_GOVERNANCE_RISK_CODES: dict[str, str] = {
    "SHARE_PLEDGE": "股权质押",
    "SHARE_REDUCTION": "股东/高管减持",
    "RELATED_PARTY": "关联交易",
    "AUDITOR_CHANGE": "审计机构变更",
    "AUDIT_QUALIFIED": "审计非标意见",  # 一票否决级（M9 VETO_RISK_CODES 消费）
    "REGULATORY_PENALTY": "监管处罚/问询",
    "CAPITAL_IMPAIRMENT": "资本配置低效/乱并购",
    "CONTROL_RISK": "股权结构/控制权风险",
    "OTHER": "其他治理风险",
}
_ALLOWED_SEVERITY = {"low", "medium", "high"}
_ALLOWED_GRADE = {"good", "neutral", "poor"}  # 6.8：档位字段（供 M10/展示消费）
_MAX_RISK_CODES = 6


def _capital_allocation_flag(score: float) -> str:
    """资本配置代理档位：基于最终治理分数（含事件扣分/LLM 校准）。"""
    if score >= 70:
        return "good"
    if score >= 55:
        return "neutral"
    return "poor"


def _clean_qualitative(parsed: dict) -> dict:
    """只保留合法字段的 LLM 定性：枚举白名单 + 风险码/严重度清洗（防幻觉字段污染下游）。"""
    out: dict = {}
    for key in ("shareholder_alignment", "capital_allocation", "disclosure_quality", "conclusion"):
        v = parsed.get(key)
        if isinstance(v, str) and v.strip():
            out[key] = v.strip()[:200]
    # 6.8：结构化档位字段（good/neutral/poor）
    for key in ("shareholder_alignment_grade", "disclosure_quality_grade"):
        v = parsed.get(key)
        if isinstance(v, str) and v in _ALLOWED_GRADE:
            out[key] = v
    risks = parsed.get("governance_risks")
    if isinstance(risks, list):
        cleaned: list[dict] = []
        for r in risks:
            if not isinstance(r, dict):
                continue
            code = r.get("code")
            sev = r.get("severity")
            if code not in _GOVERNANCE_RISK_CODES or sev not in _ALLOWED_SEVERITY:
                continue
            desc = r.get("description")
            cleaned.append({
                "code": code,
                "severity": sev,
                "description": (
                    str(desc).strip()[:120] if isinstance(desc, str) and desc.strip()
                    else _GOVERNANCE_RISK_CODES[code]
                ),
            })
        if cleaned:
            out["governance_risks"] = cleaned[:_MAX_RISK_CODES]
    return out


def _risk_signals(risk_codes: list[dict]) -> list[dict]:
    """治理风险码 → 契约 signals[]（RiskSignal 兼容：code/severity/metric/message）。"""
    return [
        {
            "code": r["code"],
            "severity": r["severity"],
            "metric": "governance",
            "message": r["description"],
        }
        for r in risk_codes
        if isinstance(r, dict) and r.get("code")
    ]


_LLM_SYSTEM = (
    "你是公司治理分析师。基于公开信息评估管理层诚信、资本配置与治理风险。"
    "规则层已给出分红/回报股东代理评分与可选治理事件信号（不完整），"
    "你的任务是结合参考资料做定性判断并输出结构化治理风险。"
    + LLM_JSON_RULE
)


class M6GovernanceAgent(Agent):
    spec = AgentSpec(
        id="M6_governance",
        name="治理与资本配置智能体",
        description="分红代理 + 治理事件 + LLM 定性（治理评级/资本配置/治理风险）",
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M6 需要数据访问（ctx.data）")
        code = ctx.session.company_code

        try:
            div = ctx.data.dividends(code)
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"分红数据获取失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "dividend_years": 0,
                    "payout_latest": None,
                    "dividend_yield": None,
                    "note": "分红数据不可用",
                    "signals": [],
                    "handoff": {
                        "governance_score": 50,  # 6.7：降级态改中性分，不再等价于「治理极差 0 分」
                        "capital_allocation_flag": "neutral",
                        "governance_risk_codes": [],
                        "reason_codes": ["DATA_UNAVAILABLE"],
                    },
                },
            )

        # 治理事件（非分红证据）：数据源未实现/未接入时按无事件中性处理
        events: dict = {}
        try:
            events = ctx.data.governance_events(code) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("M6 治理事件获取失败（%s），按无事件处理", type(exc).__name__)

        # 股息率：现价 best-effort（M6 不依赖 M4，直接从行情取最新收盘价）
        price = None
        try:
            dp = ctx.data.daily_prices(code).get("records", [])
            if dp:
                latest = max(dp, key=lambda r: str(r.get("trade_date") or ""))
                price = latest.get("close")
        except Exception as exc:  # noqa: BLE001
            logger.debug("M6 现价获取失败（%s），股息率按缺省处理", type(exc).__name__)

        try:
            result = assess_governance(div, events=events, price=price)
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"规则引擎执行失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "dividend_years": 0,
                    "payout_latest": None,
                    "dividend_yield": None,
                    "note": "治理规则引擎不可用",
                    "signals": [],
                    "handoff": {
                        "governance_score": 50,  # 6.7：降级态改中性分，不再等价于「治理极差 0 分」
                        "capital_allocation_flag": "neutral",
                        "governance_risk_codes": [],
                        "reason_codes": ["DATA_UNAVAILABLE"],
                    },
                },
            )

        evidence = list(result.evidence)
        qual: dict = {}
        llm_raw: str | None = None

        # 初始 handoff：规则层（分红代理 + 规则治理事件风险码）
        handoff = {
            "governance_score": result.score,
            "capital_allocation_flag": _capital_allocation_flag(result.score),
            "governance_risk_codes": list(result.risk_codes),
        }

        if ctx.llm is not None:
            try:
                refs = CompanyReferences().fetch(code, slot=2)  # 先抓真实链接供 LLM 筛选
                user_prompt = f"公司：{ctx.session.company_name or code}，分红信号：{result.note}。\n"
                ref_block = format_reference_list(refs)
                if ref_block:
                    user_prompt += ref_block + "\n"
                user_prompt += (
                    "请按以下结构输出 JSON：\n"
                    '{"shareholder_alignment": "股东利益一致性评估", '
                    '"capital_allocation": "资本配置评估", '
                    '"governance_risks": [{"code": "SHARE_PLEDGE", "severity": "high", '
                    '"description": "风险描述"}], '
                    '"disclosure_quality": "信息披露质量", '
                    '"conclusion": "一句话结论", '
                    '"reference_indices": [筛选出的参考文章编号(1基)]}\n'
                    "governance_risks 的 code 必须取自："
                    + "、".join(f"{k}({v})" for k, v in _GOVERNANCE_RISK_CODES.items())
                    + "；severity 只能是 low/medium/high；没有风险就输出空数组。"
                    "reference_indices：从参考资料清单中筛选与「治理/资本配置判断」最相关的文章编号"
                    "（1 基），没有就输出空数组；不得编造标题或链接。"
                    "优先选择较新的资料（新闻/研报以最近 1-2 年内为主），不要把几年前的旧资讯当作当前事实；引用时以清单中标注的日期为准。"
                )
                text = ctx.stream_llm(_LLM_SYSTEM, user_prompt)
                if not text:
                    evidence.append("LLM 调用无返回，使用规则结果")
                else:
                    parsed = parse_llm_json(text)
                    if parsed is None:
                        llm_raw = text
                        evidence.append("LLM 定性：已接入（输出解析失败，按原文展示）")
                    else:
                        qual = _clean_qualitative(parsed)
                        selected = select_references(refs, parsed.get("reference_indices"))
                        if selected:
                            qual["references"] = selected
                        if qual:
                            evidence.append("LLM 定性：已接入（结构化 JSON）")
                        else:
                            evidence.append("LLM 定性：已接入但字段全部非法，按规则结果")
            except Exception as exc:  # noqa: BLE001
                evidence.append(f"LLM 调用失败，使用规则结果：{type(exc).__name__}")
        else:
            evidence.append("未配置 LLM（LLM_API_KEY），当前为规则引擎结果")

        # LLM 合法 governance_risks → 回填 handoff.governance_risk_codes（M9 消费闭环）
        if qual.get("governance_risks"):
            handoff["governance_risk_codes"] = qual["governance_risks"]
            evidence.append(
                f"治理风险信号：{len(qual['governance_risks'])} 项已回填 handoff.governance_risk_codes"
            )
        # 6.8：结构化档位字段进 handoff（展示/下游消费）
        for grade_key in ("shareholder_alignment_grade", "disclosure_quality_grade"):
            if grade_key in qual:
                handoff[grade_key] = qual[grade_key]

        # 最终分数（llm_score 可校准）→ 回写 handoff，统一下游口径（M4/M9/M10 读同一个数）
        calib: dict = {}
        score = llm_score(
            ctx, self.spec.id,
            facts={
                "连续分红年数": result.dividend_years,
                "每股派息": result.payout_latest,
                "治理说明": result.note,
                "治理风险信号": len(handoff["governance_risk_codes"]),
            },
            evidence=evidence, default=result.score, trace=calib,
        )
        handoff["governance_score"] = score
        handoff["capital_allocation_flag"] = _capital_allocation_flag(score)

        outputs: dict = {
            "dividend_years": result.dividend_years,
            "payout_latest": result.payout_latest,
            "dividend_yield": result.dividend_yield,
            "note": result.note,
            "signals": _risk_signals(handoff["governance_risk_codes"]),
            "handoff": handoff,
        }
        if qual:
            outputs["llm_qualitative"] = qual
        elif llm_raw is not None:
            # 3.2：raw 仅调试用，截断防 API payload 膨胀
            outputs["llm_qualitative"] = llm_raw[:2000]

        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score, calibration=calib or None,
            outputs=outputs, evidence=evidence,
        )
