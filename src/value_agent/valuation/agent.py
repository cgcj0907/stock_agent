"""M4 估值智能体：取数据 → 估值引擎 → LLM 行业校准（可选）→ 输出 ModuleResult。

v2（2026-08-07）：
- 消费 M2/M3/M5/M6 输出做质量乘数 + kill switch（复用现有信号，不新造）
- DCF 用现金化利润代理（financials 表 ocf_to_np/ocfps 字段）
- outputs 新增 valuation_confidence / quality_multiplier / kill_switches / method_agreement
- 补 handoff（intrinsic_range / coverage / valuation_confidence / methods_used），对齐 09-module-contracts §4 M4
- 买卖点仍归 M8（safety_margin），M4 不重复产出 buy/sell

v3（2026-08-07）：LLM 行业校准层（可选）
- 规则估值打底 → LLM 按行业惯例校准「路由/参数/方法权重/置信度」（有界 clamp）→ 用校准重跑
- 不同行业的估值体系差异落地：business_type 覆盖 + 增速/折现率/永续 + 方法权重
- 未配 LLM 时完全退化为规则结果（现有行为不变）
"""
from __future__ import annotations

from value_agent.agents.base import DATA_SOURCE_HINT, Agent, AgentContext, AgentSpec
from value_agent.core.contracts import ReasonCode, build_meta
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import METHOD_WEIGHTS, load_routing, run_valuation

# 方法名 → 一句话说明（methods[].reason 用；note 用于跳过原因）
_METHOD_REASON = {
    "dcf": "两阶段 DCF（现金化利润基数，含敏感性：增速±2pct / 折现率∓1pct）",
    "tang": "唐朝估值法（三年后合理估值，买点 50% / 卖点 150%）",
    "graham_number": "格雷厄姆数 √(22.5×EPS×每股净资产)",
    "graham_formula": "格雷厄姆公式 EPS×(8.5+2g)×4.4/Y",
    "ddm": "股利折现（D₁/(r−g)）",
    "relative_median_pe": "历史中位 PE × EPS（周期股用正常化 EPS 并封顶 25 倍）",
    "peg": "PEG（合理 PE≈增速%，适合成长型）",
    "pb_band": "PB 估值法（每股净资产 × 历史中位 PB，周期/资产型主方法）",
    "pb_roe": "PB-ROE（每股净资产 × (ROE−g)/(r−g)，银行主方法）",
}

# M4 消费的上游模块（= ctx.inputs 实际读取集合，与 MODULE_DEPENDENCIES/YAML deps 对齐）
_QUALITY_SOURCES = ("M2_financial_quality", "M3_growth", "M5_moat", "M6_governance")
_QUALITY_KEY = {"M2_financial_quality": "m2", "M5_moat": "m5", "M3_growth": "m3", "M6_governance": "m6"}


def _module_score(module) -> float | None:
    """模块分数：优先 handoff 契约字段（governance_score），否则用外层 score。"""
    if module is None or module.outputs is None:
        return None
    handoff = module.outputs.get("handoff") or {}
    if module.module == "M6_governance" and handoff.get("governance_score") is not None:
        return handoff["governance_score"]
    return module.score


def methods_to_list(methods: dict, confidences: dict | None = None) -> list[dict]:
    """methods dict → 统一方法数组（docs/09-module-contracts.md §4 M4）。"""
    confidences = confidences or {}
    return [
        {
            "method": name,
            "applicable": m.value is not None,
            "value": m.value,
            "low": m.low,
            "high": m.high,
            "reason": (m.note or _METHOD_REASON.get(name, "")),
            "confidence": confidences.get(name, 0.0) if m.value is not None else 0.0,
        }
        for name, m in methods.items()
    ]


class M4ValuationAgent(Agent):
    spec = AgentSpec(
        id="M4_valuation",
        name="估值引擎智能体",
        description="方法路由(按生意类型) + 多模型交叉 + 质量乘数/kill_switch + LLM 行业校准",
        inputs=["M1_business_model", "M2_financial_quality", "M3_growth", "M5_moat", "M6_governance"],
        requires_llm=True,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M4 需要数据访问（ctx.data），请注入 DataManager")
        code = ctx.session.company_code
        try:
            return self._run_impl(ctx, code)
        except Exception as exc:  # noqa: BLE001
            # 数据源瞬时故障：降级为 DONE（带说明），不阻塞下游 M8/M9/M10/M11
            # 降级态字段集合与正常态一致（§3）：缺值置 None/空，meta 标记 degraded
            return ModuleResult(
                module=self.spec.id,
                status=ModuleStatus.DONE,
                score=0.0,
                outputs={
                    "business_type": "cyclical",
                    "methods": [],
                    "intrinsic_value": None,
                    "current_price": None,
                    "params": {},
                    "valuation_confidence": 0.0,
                    "quality_multiplier": None,
                    "risk_multiplier": None,
                    "total_multiplier": None,
                    "quality_tier": None,
                    "quality_score": None,
                    "kill_switches": [],
                    "method_agreement": None,
                    "weights": {},
                    "llm_qualitative": None,
                    "handoff": {
                        "intrinsic_range": None,
                        "coverage": "low",
                        "valuation_confidence": 0.0,
                        "methods_used": [],
                    },
                },
                evidence=[f"数据源异常：{type(exc).__name__}（{str(exc)[:80]}），估值降级"],
                meta=build_meta(0.0, "low", degraded=True,
                                reason_codes=[ReasonCode.DATA_UNAVAILABLE.value]),
            )

    def _run_impl(self, ctx: AgentContext, code: str) -> ModuleResult:
        # 4 个数据集各自独立拉取：任何一个失败只影响对应输入，不整模块空白；
        # 失败原因记入 fetch_notes，随 evidence 展示给用户。
        datasets: dict[str, dict | None] = {}
        fetch_notes: list[str] = []
        for key, label, fn in (
            ("fin", "财务数据", lambda: ctx.data.financials(code)),
            ("val", "估值历史", lambda: ctx.data.valuation_history(code)),
            ("price", "日线价格", lambda: ctx.data.daily_prices(code)),
            ("div", "分红数据", lambda: ctx.data.dividends(code)),
        ):
            try:
                datasets[key] = fn()
            except Exception as exc:  # noqa: BLE001
                datasets[key] = None
                fetch_notes.append(
                    f"{label}获取失败（{type(exc).__name__}：{str(exc)[:60]}），该项按缺失处理"
                )

        fin, val, price, div = (
            datasets["fin"], datasets["val"], datasets["price"], datasets["div"],
        )

        # 输入抽取：优先最新年报（季度记录按 period 倒序，避免取到最旧/亏损期）；
        # EPS/OCFPS/OCF-NP/负债率取同一年报记录，保证现金化代理口径一致（DB financials 表字段）
        fin_recs = [r for r in (fin or {}).get("records", []) if r.get("period")]
        fin_recs_sorted = sorted(
            fin_recs, key=lambda r: str(r.get("period") or ""), reverse=True
        )
        annual_rec = next(
            (r for r in fin_recs_sorted if str(r.get("period", "")).endswith("1231")),
            fin_recs_sorted[0] if fin_recs_sorted else None,
        )
        eps = annual_rec.get("eps") if annual_rec else None
        ocfps = annual_rec.get("ocfps") if annual_rec else None
        ocf_to_np = annual_rec.get("ocf_to_np") if annual_rec else None
        debt_to_assets = annual_rec.get("debt_to_assets") if annual_rec else None
        roe = annual_rec.get("roe") if annual_rec else None
        # 按 trade_date 降序取最新
        val_recs = sorted((val or {}).get("records", []), key=lambda r: r.get("trade_date") or "", reverse=True)
        price_recs = sorted((price or {}).get("records", []), key=lambda r: r.get("trade_date") or "", reverse=True)
        close = price_recs[0].get("close") if price_recs else None
        pb = next((r["pb"] for r in val_recs if r.get("pb")), None)
        bvps = close / pb if (close and pb) else None
        # 仅取正 PE：亏损期 PE 为负，会让中位数失真（相对估值无意义）
        pe_history = [
            r["pe_ttm"] for r in val_recs if r.get("pe_ttm") and r["pe_ttm"] > 0
        ]
        # 周期股正常化保护输入：年度 EPS 序列（按年份升序，取近 N 年中位）+ PB 历史（DB 字段）
        eps_history = [
            r["eps"] for r in sorted(
                (r for r in fin_recs
                 if str(r.get("period", "")).endswith("1231") and r.get("eps") and r["eps"] > 0),
                key=lambda r: str(r.get("period") or ""),
            )
        ]
        pb_history = [r["pb"] for r in val_recs if r.get("pb") and r["pb"] > 0]
        dividend = next((r["cash_div_tax"] for r in (div or {}).get("records", []) if r.get("cash_div_tax")), None)

        # 业务类型：优先 M1 输出，其次 assumptions
        m1 = ctx.inputs.get("M1_business_model")
        business_type = (
            (m1.outputs.get("business_type") if m1 and m1.outputs else None)
            or ctx.assumptions.get("business_type")
            or "cyclical"  # 未知类型保守按周期（禁 DCF/唐朝，避免增长假设拉宽区间）
        )
        industry = (m1.outputs.get("industry") if m1 and m1.outputs else None) or ""
        financial_subtype = (
            (m1.outputs.get("handoff") or {}).get("financial_subtype")
            if m1 and m1.outputs else None
        )
        company_name = ctx.session.company_name or code

        params = {k: ctx.assumptions[k] for k in
                  ("growth_rate", "discount_rate", "terminal_growth", "risk_free_rate")
                  if k in ctx.assumptions}
        # M3 提供的增速估计优先（用户 assumptions 显式覆盖除外）
        m3 = ctx.inputs.get("M3_growth")
        if m3 and m3.outputs:
            m3_handoff = m3.outputs.get("handoff") or {}
            if m3.outputs.get("growth_estimate") is not None and "growth_rate" not in ctx.assumptions:
                # 4.4：M3 给出增速情景区间时，DCF 采用保守档（降低乐观外推）
                scenarios = m3_handoff.get("growth_scenarios") or {}
                conservative = scenarios.get("conservative")
                params["growth_rate"] = (
                    conservative if conservative is not None
                    else m3.outputs["growth_estimate"]
                )
            if m3_handoff.get("growth_confidence"):
                params["growth_confidence"] = m3_handoff["growth_confidence"]

        # 质量乘数 + kill switch 输入：全部来自 M2/M3/M5/M6 既有输出（缺失则 None/中性）
        quality = {}
        for mod_id in _QUALITY_SOURCES:
            mod = ctx.inputs.get(mod_id)
            quality[_QUALITY_KEY[mod_id]] = _module_score(mod)
        m2 = ctx.inputs.get("M2_financial_quality")
        m2_signals = [
            s.get("code") for s in (m2.outputs.get("signals") or []) if isinstance(s, dict) and s.get("code")
        ] if m2 and m2.outputs else []
        m3_cyclicality = m3_handoff.get("cyclicality_flag") if m3 and m3.outputs else None
        m3_prosperity = m3_handoff.get("prosperity_code") if m3 and m3.outputs else None
        m5 = ctx.inputs.get("M5_moat")
        m5_width = (m5.outputs.get("handoff") or {}).get("moat_width") if m5 and m5.outputs else None
        m6 = ctx.inputs.get("M6_governance")
        m6_score = (m6.outputs.get("handoff") or {}).get("governance_score") if m6 and m6.outputs else None

        # 估值引擎入参（规则 + LLM 校准共用一份，避免两处口径漂移）
        valuation_kwargs = {
            "eps": eps, "bvps": bvps, "pe_history": pe_history, "dividend": dividend,
            "business_type": business_type, "params": params,
            "ocfps": ocfps, "ocf_to_np": ocf_to_np, "debt_to_assets": debt_to_assets,
            "quality": quality, "m2_signals": m2_signals,
            "m3_cyclicality_flag": m3_cyclicality, "m3_prosperity_code": m3_prosperity,
            "m5_width": m5_width, "m6_score": m6_score,
            "eps_history": eps_history, "pb_history": pb_history,
            "roe": roe, "financial_subtype": financial_subtype,
        }
        result = run_valuation(**valuation_kwargs)

        # LLM 行业校准（可选）：规则打底 → LLM 按行业校准 → 用校准重跑
        llm_qualitative = None
        llm_evidence: list[str] = []
        if ctx.llm is not None:
            try:
                llm_qualitative, calib_result, calib_evidence = self._llm_calibrate(
                    ctx, code, company_name, industry, result, valuation_kwargs
                )
                llm_evidence += calib_evidence
                if calib_result is not None:
                    result = calib_result
                    llm_evidence.append("LLM 行业校准：已接入（结构化 JSON，结果已按校准重跑）")
            except Exception as exc:  # noqa: BLE001
                llm_evidence.append(f"LLM 行业校准调用失败，使用规则结果：{type(exc).__name__}")
        else:
            llm_evidence.append("未配置 LLM（LLM_API_KEY），当前为规则引擎结果")

        score = llm_score(
            ctx, self.spec.id,
            facts={
                "生意类型": business_type,
                "行业": industry,
                "EPS": eps,
                "现价": close,
                "方法覆盖分": result.coverage_score,
                "估值置信度": result.valuation_confidence,
                "质量乘数": result.quality_multiplier,
            },
            evidence=result.evidence, default=result.coverage_score,
        )
        evidence = fetch_notes + result.evidence + llm_evidence
        if fetch_notes:
            evidence.append(DATA_SOURCE_HINT)
        meta = {}
        if fetch_notes:
            meta = build_meta(
                result.coverage_score / 100.0,
                "low",
                degraded=True,
                reason_codes=[ReasonCode.DATA_UNAVAILABLE.value],
            )
        return ModuleResult(
            module=self.spec.id,
            status=ModuleStatus.DONE,
            score=score,
            outputs={
                "business_type": result.business_type,
                "methods": methods_to_list(result.methods, result.method_confidences),
                "intrinsic_value": result.intrinsic,
                "current_price": close,
                "params": result.params,
                "valuation_confidence": result.valuation_confidence,
                "quality_multiplier": result.quality_multiplier,
                "risk_multiplier": result.risk_multiplier,
                "total_multiplier": result.total_multiplier,
                "quality_tier": result.quality_tier,
                "quality_score": result.quality_score,
                "kill_switches": result.kill_switches,
                "method_agreement": result.method_agreement,
                "weights": result.weights,
                "llm_qualitative": llm_qualitative,
                # 下游契约（§4 M4）：M8/M10 消费 intrinsic_range / valuation_confidence
                "handoff": {
                    "intrinsic_range": {
                        "low": result.intrinsic.get("low"),
                        "mid": result.intrinsic.get("mid"),
                        "high": result.intrinsic.get("high"),
                    },
                    "coverage": (
                        "high" if result.coverage_score >= 80
                        else "medium" if result.coverage_score >= 50 else "low"
                    ),
                    "valuation_confidence": result.valuation_confidence,
                    "methods_used": list(result.methods.keys()),
                    "quality_multiplier": result.quality_multiplier,
                    "kill_switches": result.kill_switches,
                },
            },
            evidence=evidence,
            meta=meta,
        )

    def _llm_calibrate(
        self,
        ctx: AgentContext,
        code: str,
        company_name: str,
        industry: str,
        base,
        valuation_kwargs: dict,
    ) -> tuple[dict | None, object | None, list[str]]:
        """LLM 行业校准：组装上下文 → 调 LLM → 解析/clamp → 用校准参数重跑引擎。

        返回 (qualitative_dict, calibrated_result|None, evidence_lines)：
        - 解析失败/空校准 → (None, None, [说明])，调用方保持规则结果
        - 成功 → (qualitative, calibrated, [校准摘要])
        所有数值调整在 valuation/llm.py 里 clamp 到安全区间。
        """
        from value_agent.data.references import CompanyReferences, format_reference_list

        from .llm import (
            INDUSTRY_CALIBRATION_SYSTEM,
            apply_calibration,
            build_calibration_prompt,
            parse_calibration,
        )

        refs_block = ""
        try:
            refs = CompanyReferences().fetch(code, slot=3)
            if refs:
                refs_block = format_reference_list(refs)
        except Exception:  # noqa: BLE001
            refs_block = ""

        upstream: dict[str, str] = {}
        m2 = ctx.inputs.get("M2_financial_quality")
        if m2 and m2.outputs:
            codes = [s.get("code", "") for s in (m2.outputs.get("signals") or []) if isinstance(s, dict)]
            upstream["M2 财务质量"] = f"{m2.score or '—'}/100，信号：{', '.join(codes) or '无'}"
        m3 = ctx.inputs.get("M3_growth")
        if m3 and m3.outputs:
            h = m3.outputs.get("handoff") or {}
            upstream["M3 成长"] = (
                f"增速 {m3.outputs.get('growth_estimate')}，景气 {h.get('prosperity_code')}，"
                f"周期flag {h.get('cyclicality_flag')}，信心 {h.get('growth_confidence')}"
            )
        m5 = ctx.inputs.get("M5_moat")
        if m5 and m5.outputs:
            upstream["M5 护城河"] = f"{m5.outputs.get('width')}（{(m5.outputs.get('handoff') or {}).get('moat_width')}）"
        m6 = ctx.inputs.get("M6_governance")
        if m6 and m6.outputs:
            upstream["M6 治理"] = f"{(m6.outputs.get('handoff') or {}).get('governance_score')}/100"

        method_lines = [
            f"{m.name}: {m.value} 元" if m.value is not None else f"{m.name}: 跳过（{m.note}）"
            for m in base.methods.values()
        ]
        prompt = build_calibration_prompt(
            company_name=company_name, code=code, industry=industry or "",
            business_type=base.business_type,
            allowed=list(base.methods.keys()) or [base.business_type],
            method_lines=method_lines,
            intrinsic=base.intrinsic, confidence=base.valuation_confidence,
            params=base.params, upstream=upstream, refs_block=refs_block,
        )
        text = ctx.stream_llm(INDUSTRY_CALIBRATION_SYSTEM, prompt)
        calib = parse_calibration(text)
        if not calib:
            return None, None, ["LLM 行业校准：输出解析失败或无可调整项，保持规则结果"]
        # 权重校准只作用于「最终路由」的方法：忽略如周期股上 DCF 这类未路由权重（无效配置）
        bt2 = calib.get("business_type_override")  # 已由 clamp_calibration 校验
        final_bt = bt2 or valuation_kwargs["business_type"]
        routed = set(load_routing().get(final_bt, []))
        raw_weights = calib.get("method_weight_adjustments") or {}
        filtered_weights = {k: v for k, v in raw_weights.items() if k in routed}
        dropped_weights = sorted(set(raw_weights) - routed)
        calib["method_weight_adjustments"] = filtered_weights or None
        p2, w2, bt2, delta = apply_calibration(base.params, base.weights or METHOD_WEIGHTS, calib)
        calibrated = run_valuation(
            **{
                **valuation_kwargs,
                "business_type": bt2 or valuation_kwargs["business_type"],
                "params": p2,
                "weights": w2,
                "confidence_delta": delta,
            }
        )
        # 校准摘要挂到 qualitative，随 evidence 展示
        notes = {
            "business_type_override": bt2,
            "route_confidence": calib.get("route_confidence"),
            "parameter_adjustments": calib.get("parameter_adjustments"),
            "method_weight_adjustments": calib.get("method_weight_adjustments"),
            "valuation_confidence_delta": calib.get("valuation_confidence_delta"),
            "industry_notes": calib.get("industry_notes", []),
            "risk_notes": calib.get("risk_notes", []),
            "reasons": calib.get("reasons", []),
            "calibrated_intrinsic": calibrated.intrinsic,
        }
        qualitative = {"calibration": notes, "raw": text}
        detail: list[str] = []
        if bt2:
            detail.append(f"  · 路由覆盖：{valuation_kwargs['business_type']} → {bt2}")
        if dropped_weights:
            detail.append(f"  · 忽略未路由方法的权重调整：{', '.join(dropped_weights)}")
        changed_params = {k: v for k, v in p2.items() if base.params.get(k) != v}
        if changed_params:
            detail.append(f"  · 参数校准：{changed_params}")
        changed_weights = {k: v for k, v in w2.items() if METHOD_WEIGHTS.get(k) != v}
        if changed_weights:
            detail.append(f"  · 权重校准：{changed_weights}")
        if delta:
            detail.append(f"  · 置信度增量：{delta:+.2f}")
        for key in ("reasons", "industry_notes", "risk_notes"):
            for line in calib.get(key, []):
                detail.append(f"  · {line}")
        return qualitative, calibrated, detail
