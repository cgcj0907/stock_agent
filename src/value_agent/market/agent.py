"""M7 价格与情绪智能体。"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from value_agent.agents.base import Agent, AgentContext, AgentSpec, degraded_module_result
from value_agent.core.scoring import llm_score
from value_agent.sessions.models import ModuleResult, ModuleStatus

from .engine import assess_market, sentiment_from_daily


def _percentile_metric(records: list[dict], value_key: str, note: str, unit: str = "") -> dict | None:
    """历史序列 → 最新值分位指标（7.1/7.2）：样本 ≥5 才给分位，否则 None（降级为中性）。"""
    recs = sorted(
        (r for r in records if r.get("trade_date") and r.get(value_key) is not None),
        key=lambda r: str(r["trade_date"]), reverse=True,
    )
    if len(recs) < 5:
        return None
    hist = [float(r[value_key]) for r in recs]
    latest = hist[0]
    from .engine import _percentile, _winsorize

    return {
        "latest": latest,
        "percentile": _percentile(latest, _winsorize(hist)),
        "note": note,
        "unit": unit,
    }


def _valuation_percentile(result) -> float | None:
    """估值分位 = max(PE 分位, PB 分位)，供 M8/M10 消费。"""
    vals = [p for p in (result.pe_percentile, result.pb_percentile) if p is not None]
    return max(vals) if vals else None


def _market_state(position: str) -> str:
    """价格位置 → 契约枚举（overheated/normal/cold/insufficient）。"""
    if position in ("极低估", "低估"):
        return "cold"
    if position == "合理":
        return "normal"
    if position in ("高估", "泡沫"):
        return "overheated"
    return "insufficient"


def _margin_adjustment(position: str, heat: float | None = None) -> float:
    """安全边际折扣调整量：过热 +5pct、样本不足 +10pct（保守）、正常 0、低估 −5pct。

    7.10：高估/泡沫 + 情绪过热（heat ≥ 0.66）→ 额外 +5pct（接飞刀/追涨更保守）。
    """
    base = {
        "极低估": -0.05,
        "低估": -0.05,
        "合理": 0.0,
        "高估": 0.05,
        "泡沫": 0.05,
        "样本不足（<10 期）": 0.10,
    }.get(position, 0.0)
    if position in ("高估", "泡沫") and heat is not None and heat >= 0.66:
        base += 0.05
    return base


class M7MarketAgent(Agent):
    spec = AgentSpec(
        id="M7_market",
        name="价格与情绪智能体",
        description="估值历史分位 + 股债性价比 + 情绪叠加（换手率）",
        inputs=["M1_business_model"],  # 生意类型 → 主指标（周期/银行看 PB）
        requires_llm=False,
    )

    def run(self, ctx: AgentContext) -> ModuleResult:
        if ctx.data is None:
            raise RuntimeError("M7 需要数据访问（ctx.data）")
        try:
            val = ctx.data.valuation_history(ctx.session.company_code)
            risk_free = ctx.assumptions.get("risk_free_rate", 0.04)
            m1 = ctx.inputs.get("M1_business_model")
            business_type = m1.outputs.get("business_type") if m1 else None
            financial_subtype = m1.outputs.get("financial_subtype") if m1 else None

            # 情绪指标（7.12 多指标合成）：换手率（日线）+ 北向持股（7.1）+ 两融余额（7.2）
            # + 大盘涨跌家数（7.5）；各自拉取失败只丢该指标，不降级整个模块
            metrics: dict[str, dict] = {}
            notes: list[str] = []
            try:
                dp = ctx.data.daily_prices(ctx.session.company_code)
                daily_sent = sentiment_from_daily(dp.get("records", []))
                if daily_sent:
                    metrics.update(daily_sent.get("metrics", {}))
                    notes.extend(daily_sent.get("notes", []))
            except Exception as exc:  # noqa: BLE001
                logger.debug("M7 换手率情绪获取失败：%s", type(exc).__name__)
            try:
                nb = ctx.data.northbound(ctx.session.company_code)
                m = _percentile_metric(nb.get("records", []), "hold_ratio", "北向持股比例", "%")
                if m is not None:
                    metrics["northbound"] = m
            except Exception as exc:  # noqa: BLE001
                logger.debug("M7 北向持股获取失败：%s", type(exc).__name__)
            try:
                mg = ctx.data.margin(ctx.session.company_code)
                m = _percentile_metric(mg.get("records", []), "margin_balance", "融资融券余额", "元")
                if m is not None:
                    metrics["margin"] = m
            except Exception as exc:  # noqa: BLE001
                logger.debug("M7 两融余额获取失败：%s", type(exc).__name__)
            try:
                ma = ctx.data.market_activity()
                recs = ma.get("records", [])
                if recs and recs[0].get("breadth") is not None:
                    metrics["market_breadth"] = {
                        "latest": recs[0]["breadth"],
                        "percentile": float(recs[0]["breadth"]),  # 0~1 直接作为热度
                        "note": "全市场上涨家数占比（大盘情绪）",
                        "unit": "",
                    }
            except Exception as exc:  # noqa: BLE001
                logger.debug("M7 大盘情绪获取失败：%s", type(exc).__name__)
            sentiment = {"metrics": metrics, "notes": notes} if metrics else None

            result = assess_market(
                val, risk_free=risk_free,
                business_type=business_type, financial_subtype=financial_subtype,
                sentiment=sentiment,
            )
        except Exception as exc:  # noqa: BLE001
            return degraded_module_result(
                self.spec.id,
                f"估值历史获取失败（{type(exc).__name__}：{str(exc)[:60]}），已降级",
                outputs={
                    "pe_percentile": None,
                    "pb_percentile": None,
                    "position": "样本不足（<10 期）",
                    "handoff": {
                        "valuation_percentile": None,
                        "market_state": "insufficient",
                        "margin_adjustment": 0.10,
                    },
                },
            )
        # 7.10：高估 + 情绪过热 → 额外保守调整（在 handoff 上叠加，M8 直接消费）
        margin_adjustment = _margin_adjustment(result.position, result.sentiment_heat)
        if margin_adjustment != _margin_adjustment(result.position):
            result.evidence.append(
                f"⚠️ 高估 + 情绪过热（热度 {result.sentiment_heat:.0%} ≥ 66%）：margin_adjustment 额外 +5pct"
            )
        calib: dict = {}
        score = llm_score(
            ctx, self.spec.id,
            facts={
                "PE 分位": result.pe_percentile,
                "PB 分位": result.pb_percentile,
                "价格位置": result.position,
                "情绪热度": result.sentiment_heat,
            },
            evidence=result.evidence, default=result.score, trace=calib,
        )
        sentiment_signals = [
            e for e in result.evidence if e.startswith("情绪：")
        ]
        return ModuleResult(
            module=self.spec.id, status=ModuleStatus.DONE, score=score, calibration=calib or None,
            outputs={
                "pe_percentile": result.pe_percentile,
                "pb_percentile": result.pb_percentile,
                "position": result.position,
                "sentiment_heat": result.sentiment_heat,
                "sentiment_signals": sentiment_signals,
                # 下游契约（§4 M7）：M8 消费 margin_adjustment，M10 消费 market_state
                "handoff": {
                    "valuation_percentile": _valuation_percentile(result),
                    "market_state": _market_state(result.position),
                    "margin_adjustment": margin_adjustment,
                    "sentiment_heat": result.sentiment_heat,
                },
            },
            evidence=result.evidence,
        )
