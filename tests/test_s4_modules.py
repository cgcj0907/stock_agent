"""S4 模块单元测试：M3 成长 / M7 价格情绪 / M9 风险。"""
import pytest

from value_agent.growth.engine import assess_growth
from value_agent.market.engine import _trim, assess_market, sentiment_from_daily
from value_agent.risk.engine import assess_risk
from value_agent.sessions.models import ModuleResult, ModuleStatus, Session, SessionStatus


# ---- M3 ----
def test_growth_estimate_from_eps_cagr():
    recs = [{"period": f"{2026 - i}1231", "eps": 4.0 * (1.1 ** (9 - i)), "roe": 20, "debt_to_assets": 0.3} for i in range(10)]
    r = assess_growth({"records": recs})
    assert r.growth_estimate == pytest.approx(0.10, abs=0.02)
    assert r.prosperity in ("上行", "平稳")


def test_growth_decline_prosperity_down():
    # 最新期(2026) EPS 低于最早期(2017) → 增速为负 → 下行
    recs = [{"period": f"{2026 - i}1231", "eps": 2.3 + i * 0.3, "roe": 12, "debt_to_assets": 0.4} for i in range(10)]
    r = assess_growth({"records": recs})
    assert r.prosperity == "下行"
    assert r.growth_estimate < 0.05


def test_growth_caps_at_20pct():
    recs = [{"period": f"{2026 - i}1231", "eps": 1.0 * (1.5 ** (9 - i)), "roe": 30, "debt_to_assets": 0.2} for i in range(10)]
    assert assess_growth({"records": recs}).growth_estimate <= 0.20


def test_growth_no_eps_uses_default_not_crash():
    # 回归：无 EPS 时走默认增速，不再抛 UnboundLocalError（原实现 cagr 未初始化）
    r = assess_growth({"records": [{"period": "20251231", "eps": None, "roe": 15, "debt_to_assets": 0.3}]})
    assert r.growth_estimate == pytest.approx(0.10)
    assert r.growth_confidence == "low"
    assert r.prosperity == "平稳" and r.prosperity_code == "flat"


def test_growth_empty_records_uses_default():
    r = assess_growth({"records": []})
    assert r.growth_estimate == pytest.approx(0.10)
    assert r.growth_confidence == "low"
    assert r.prosperity_code in ("up", "flat", "down")


def test_growth_flat_eps_stable_roe_is_flat_not_down():
    # 成熟稳定公司：EPS 持平、ROE 稳定 → 平稳，而非"下行"（避免 M9/M11 假警报）
    recs = [{"period": f"{2026 - i}1231", "eps": 4.0, "roe": 18, "debt_to_assets": 0.3} for i in range(8)]
    r = assess_growth({"records": recs})
    assert r.prosperity == "平稳"
    assert r.prosperity_code == "flat"


def test_growth_roe_deterioration_down():
    # ROE 同比下滑 ≥5pp（即使 EPS 持平）→ 下行
    recs = [{"period": f"{2026 - i}1231", "eps": 4.0, "roe": 18, "debt_to_assets": 0.3} for i in range(8)]
    recs[0]["roe"] = 10  # 最新一年 18 → 10
    r = assess_growth({"records": recs})
    assert r.prosperity == "下行"
    assert r.prosperity_code == "down"


# ---- M7 ----
def test_market_insufficient_samples():
    r = assess_market({"records": [{"trade_date": "20260731", "pe_ttm": 20, "pb": 3}, {"trade_date": "20260803", "pe_ttm": 21, "pb": 3.1}]})
    assert r.position == "样本不足（<10 期）"
    assert r.score == 50.0


def test_market_percentile_position():
    import datetime
    import random

    random.seed(1)
    base = datetime.date(2025, 1, 1)
    recs = [
        {
            "trade_date": (base + datetime.timedelta(days=i)).strftime("%Y%m%d"),
            "pe_ttm": random.uniform(10, 40),
            "pb": random.uniform(2, 5),
        }
        for i in range(100)  # 100 个连续有效交易日
    ]
    recs[-1]["pe_ttm"] = 15.0   # 当前低分位
    recs[-1]["pb"] = 2.2
    r = assess_market({"records": recs})
    assert r.pe_percentile is not None
    assert r.position in ("极低估", "低估")


def test_market_overvalued_high_percentile():
    recs = [
        {"trade_date": f"202501{i:02d}", "pe_ttm": 10 + i * 0.1, "pb": 2 + i * 0.02}
        for i in range(1, 101)
    ]
    r = assess_market({"records": recs})
    assert r.position in ("高估", "泡沫")


def test_market_pb_only_fallback_when_pe_insufficient():
    """银行/资产型：PE 样本不足但 PB 完整 → 用 PB 分位，不再误判"样本不足"。"""
    recs = [
        {"trade_date": f"202501{i:02d}", "pb": 0.5 + i * 0.02}
        for i in range(1, 51)
    ]
    r = assess_market({"records": recs})
    assert r.pe_percentile is None
    assert r.pb_percentile is not None
    assert r.position in ("高估", "泡沫")  # 最新 PB 分位最高
    assert any("PB 分位" in e for e in r.evidence)


def test_market_pb_only_low_percentile_is_cheap():
    recs = [
        {"trade_date": f"202501{i:02d}", "pb": 3.0 - i * 0.01}
        for i in range(1, 51)
    ]
    r = assess_market({"records": recs})
    assert r.pe_percentile is None
    assert r.pb_percentile is not None
    assert r.position in ("极低估", "低估")


def test_market_pe_only_when_pb_missing():
    """PB 缺失但 PE 完整 → 仍用 PE 分位（现状保持）。"""
    recs = [
        {"trade_date": f"202501{i:02d}", "pe_ttm": 10 + i * 0.1}
        for i in range(1, 51)
    ]
    r = assess_market({"records": recs})
    assert r.pe_percentile is not None
    assert r.pb_percentile is None
    assert r.position in ("高估", "泡沫")


def test_market_window_keeps_only_recent_10y():
    """10 年口径：2010 年的旧样本应被窗口过滤，不进入分位。"""
    recs = [
        {"trade_date": f"2010{i:02d}15", "pe_ttm": 60.0, "pb": 8.0}
        for i in range(1, 11)
    ] + [
        {"trade_date": f"2025{i:02d}15", "pe_ttm": 20.0 - i, "pb": 3.0 - i * 0.1}
        for i in range(1, 11)
    ]
    r = assess_market({"records": recs})
    assert r.position in ("极低估", "低估")
    assert any("近10年 PE 10 期 / PB 10 期" in e for e in r.evidence)


def test_market_cyclical_prefers_pb_over_pe():
    """周期股主指标 = PB：PB 低估但 PE 高 → 不再被 max() 误伤成高估/泡沫。"""
    recs = [
        {"trade_date": f"202401{i:02d}", "pe_ttm": 8 + i * 0.2, "pb": 3.0 - i * 0.05}
        for i in range(1, 31)
    ]
    r = assess_market({"records": recs}, business_type="cyclical")
    assert r.position in ("极低估", "低估")
    assert any("主指标 PB" in e for e in r.evidence)


def test_market_bank_prefers_pb():
    """银行（financial_subtype=bank）主指标 = PB。"""
    recs = [
        {"trade_date": f"202401{i:02d}", "pe_ttm": 6 + i * 0.1, "pb": 1.2 - i * 0.01}
        for i in range(1, 31)
    ]
    r = assess_market({"records": recs}, business_type="financial", financial_subtype="bank")
    assert r.position in ("极低估", "低估")
    assert any("主指标 PB" in e for e in r.evidence)


def test_market_primary_fallback_when_primary_missing():
    """主指标 PB 缺失 → 回退 PE 判定，不判样本不足。"""
    recs = [
        {"trade_date": f"202401{i:02d}", "pe_ttm": 10 + i * 0.1}
        for i in range(1, 31)
    ]
    r = assess_market({"records": recs}, business_type="cyclical")
    assert r.position in ("高估", "泡沫")
    assert any("回退" in e for e in r.evidence)


def _flat_records(n: int = 20) -> list[dict]:
    return [
        {"trade_date": f"2024{i:02d}01", "pe_ttm": 20.0, "pb": 4.0}
        for i in range(1, n + 1)
    ]


def test_market_sentiment_hot_lowers_score():
    """情绪偏热（贪婪）→ 同一估值下评分 −5。"""
    r = assess_market(
        {"records": _flat_records()},
        sentiment={"metrics": {"turnover": {"latest": 5.0, "percentile": 0.9, "note": "换手率", "unit": "%"}}},
    )
    assert r.position == "泡沫"
    assert r.sentiment_heat == 0.9
    assert r.score == 5  # 10 − 5
    assert any("贪婪" in e for e in r.evidence)


def test_market_sentiment_cold_raises_score():
    """情绪偏冷（恐惧）→ 同一估值下评分 +5。"""
    r = assess_market(
        {"records": _flat_records()},
        sentiment={"metrics": {"turnover": {"latest": 0.8, "percentile": 0.1, "note": "换手率", "unit": "%"}}},
    )
    assert r.position == "泡沫"
    assert r.sentiment_heat == pytest.approx(0.1)
    assert r.score == 15
    assert any("恐惧" in e for e in r.evidence)


def test_market_sentiment_neutral_keeps_score():
    r = assess_market(
        {"records": _flat_records()},
        sentiment={"metrics": {"turnover": {"latest": 2.0, "percentile": 0.5, "note": "换手率", "unit": "%"}}},
    )
    assert r.score == 10
    assert any("中性" in e for e in r.evidence)


def test_market_no_sentiment_notes_missing():
    r = assess_market({"records": _flat_records()})
    assert r.sentiment_heat is None
    assert r.score == 10
    assert any("情绪指标未接入" in e for e in r.evidence)


def test_sentiment_from_daily_turnover():
    """换手率序列 → 最新换手率分位；样本不足返回 None。"""
    recs = [
        {"trade_date": f"20250{i:02d}01", "turnover": 5.0 - i * 0.1, "close": 10.0}
        for i in range(1, 31)
    ]
    sent = sentiment_from_daily(recs)
    assert sent is not None
    assert sent["metrics"]["turnover"]["latest"] == pytest.approx(5.0 - 30 * 0.1)
    assert sent["metrics"]["turnover"]["percentile"] <= 0.2
    assert sentiment_from_daily(recs[:5]) is None


def test_market_outlier_winsorize():
    """7.8：异常期剔除升级为 winsorize——极端值拉回分位边界而非删除，小样本不裁剪。"""
    hist = [10.0] * 198 + [1000.0, 2000.0]
    trimmed = _trim(hist)
    assert len(trimmed) == 200          # winsorize 不删样本
    assert max(trimmed) == 1000.0       # 2000.0 被拉回 99 分位边界
    assert _trim([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]


# ---- M9 ----
def _mod(agent_id: str, outputs: dict, score: float | None = 50.0) -> ModuleResult:
    return ModuleResult(module=agent_id, status=ModuleStatus.DONE, score=score, outputs=outputs)


def test_risk_aggregates_and_veto():
    inputs = {
        "M2_financial_quality": _mod(
            "M2_financial_quality",
            {"signals": [
                {"code": "ROE_SPIKE", "severity": "medium", "metric": "roe", "message": "ROE 单年突变"},
            ], "score": 100},
            100,
        ),
        "M3_growth": _mod("M3_growth", {
            "prosperity": "下行", "growth_estimate": 0.0,
            "handoff": {"prosperity_code": "down"},
        }),
        "M5_moat": _mod("M5_moat", {"width": "无"}),
        "M6_governance": _mod("M6_governance", {
            "handoff": {"governance_score": 60, "governance_risk_codes": []},
        }, 60),
        "M7_market": _mod("M7_market", {"position": "泡沫"}),
        "M8_safety_margin": _mod("M8_safety_margin", {"discount": -0.3}, 10),
    }
    r = assess_risk(inputs)
    # Risk Registry：对象化（id/category/severity/source_module/trigger/impact）
    assert all({"id", "category", "severity", "source_module", "trigger", "impact"} <= set(x) for x in r.risk_items)
    assert any("ROE 单年突变" in x["impact"] for x in r.risk_items)  # 结构化信号按 message 消费
    assert any("护城河" in x["impact"] for x in r.risk_items)
    assert any("泡沫" in x["impact"] for x in r.risk_items)
    assert any(x["category"] == "景气" and x["trigger"] == "prosperity_code=down" for x in r.risk_items)
    assert r.veto == []  # 兼容列表
    assert r.vetoes == []
    assert sorted(r.monitor_candidates) == ["R-004", "R-005"]  # 泡沫(high) + 安全边际(high) 进入监控候选


def test_risk_veto_on_bad_financials():
    """回归：M2 分数在 handoff.quality_score / ModuleResult.score，不在 outputs["score"].

    旧实现读 outputs["score"]，而真实 M2 agent 从不输出该键 → M2<30 否决生产恒不触发。
    这里用真实 agent 输出形状（handoff.quality_score + score 在结果层）。
    """
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "metrics": {"debt_to_assets_latest": 0.3},
            "signals": [],
            "handoff": {"quality_score": 20, "risk_signal_codes": []},
        }, 20),
    }
    r = assess_risk(inputs)
    assert any("财务质量极差" in v for v in r.veto)
    assert r.vetoes[0]["id"] == "V-001"


def test_risk_veto_falls_back_to_module_score_without_handoff():
    """降级/旧输出无 handoff 时，M9 回退 ModuleResult.score（防契约缺失静默失效）。"""
    inputs = {
        "M2_financial_quality": _mod(
            "M2_financial_quality", {"metrics": {}, "signals": []}, 20
        ),
    }
    r = assess_risk(inputs)
    assert any("财务质量极差" in v for v in r.veto)


def test_risk_consumes_moat_erosion_risks():
    """M9 真正消费 M5 handoff 的 erosion_risks/moat_durability（契约闭环，不再只看 width）。"""
    inputs = {
        "M5_moat": _mod("M5_moat", {
            "width": "中",
            "handoff": {
                "moat_width": "medium",
                "moat_durability": "low",
                "moat_trend": "eroding",
                "erosion_risks": ["新进入者低价竞争", "技术路线被替代"],
            },
        }),
    }
    r = assess_risk(inputs)
    erosion_items = [
        it for it in r.risk_items
        if it["category"] == "护城河" and it["trigger"] == "erosion_risk"
    ]
    assert len(erosion_items) == 2
    assert any("低价竞争" in it["impact"] for it in erosion_items)
    # 5.13：durability=low + trend=eroding → critical（接近一票否决）→ 进 M11 监控候选
    assert all(it["severity"] == "critical" for it in erosion_items)
    assert all(it["id"] in r.monitor_candidates for it in erosion_items)


def test_risk_moat_erosion_medium_when_durable():
    """durability=high 时侵蚀风险为 medium，不进入监控候选。"""
    inputs = {
        "M5_moat": _mod("M5_moat", {
            "width": "宽",
            "handoff": {
                "moat_width": "wide",
                "moat_durability": "high",
                "erosion_risks": ["新进入者低价竞争"],
            },
        }),
    }
    r = assess_risk(inputs)
    erosion_items = [it for it in r.risk_items if it["trigger"] == "erosion_risk"]
    assert len(erosion_items) == 1
    assert erosion_items[0]["severity"] == "medium"
    assert erosion_items[0]["id"] not in r.monitor_candidates


def test_risk_consumes_m6_governance_score():
    """M9 读 handoff.governance_score（契约字段），而非不存在的 outputs["score"].

    回归：旧版读 outputs["score"]，而 M6 分数在 ModuleResult.score，生产分支恒不触发。
    """
    inputs = {
        "M6_governance": _mod("M6_governance", {
            "dividend_years": 0,
            "handoff": {"governance_score": 30, "governance_risk_codes": []},
        }, 30),
    }
    r = assess_risk(inputs)
    gov = [it for it in r.risk_items if it["category"] == "治理"]
    assert any(it["trigger"] == "governance_score<55" for it in gov)
    assert any("回报股东偏弱" in it["impact"] for it in gov)


def test_risk_consumes_m6_governance_risk_codes():
    """M9 消费 M6 handoff.governance_risk_codes：severity 进入 Risk Registry，high 进监控候选。"""
    inputs = {
        "M6_governance": _mod("M6_governance", {
            "handoff": {
                "governance_score": 75,
                "governance_risk_codes": [
                    {"code": "REGULATORY_PENALTY", "severity": "high",
                     "description": "因信披违规被处罚"},
                    {"code": "SHARE_REDUCTION", "severity": "medium",
                     "description": "控股股东计划减持"},
                    "不是对象",
                    {"severity": "high", "description": "缺 code 的结构脏数据"},
                ],
            },
        }, 75),
    }
    r = assess_risk(inputs)
    risk_items = [it for it in r.risk_items if it["source_module"] == "M6_governance"]
    triggers = {it["trigger"] for it in risk_items}
    assert "governance_risk_code=REGULATORY_PENALTY" in triggers
    assert "governance_risk_code=SHARE_REDUCTION" in triggers
    # 结构脏数据（非 dict / 缺 code）被跳过
    assert len(risk_items) == 2
    reg = next(it for it in risk_items if it["trigger"] == "governance_risk_code=REGULATORY_PENALTY")
    assert reg["severity"] == "high"
    assert reg["id"] in r.monitor_candidates  # high → M11 监控候选
    assert any("信披违规" in it["impact"] for it in risk_items)


def test_risk_moat_erosion_severity_tiers():
    """5.13：侵蚀风险 severity 三档 —— low+eroding→critical / 单条件→high / 否则 medium。"""
    def run(durability, trend):
        inputs = {
            "M5_moat": _mod("M5_moat", {
                "width": "中",
                "handoff": {
                    "moat_width": "medium",
                    "moat_durability": durability,
                    "moat_trend": trend,
                    "erosion_risks": ["行业竞争加剧"],
                },
            }),
        }
        r = assess_risk(inputs)
        return next(it["severity"] for it in r.risk_items if it["trigger"] == "erosion_risk")

    assert run("low", "eroding") == "critical"
    assert run("low", "stable") == "high"
    assert run("high", "eroding") == "high"
    assert run("high", "stable") == "medium"
    # 缺 trend（旧输出）→ 按 durability 兜底
    inputs = {
        "M5_moat": _mod("M5_moat", {
            "width": "中",
            "handoff": {"moat_width": "medium", "moat_durability": "low",
                        "erosion_risks": ["行业竞争加剧"]},
        }),
    }
    r = assess_risk(inputs)
    assert next(it["severity"] for it in r.risk_items if it["trigger"] == "erosion_risk") == "high"


def test_risk_assumption_veto():
    r = assess_risk({}, assumptions={"veto_reasons": ["pledge_ratio_gt_80"]})
    assert r.veto == ["pledge_ratio_gt_80"]
    assert r.score < 100



def test_risk_veto_fraud_signal_combo():
    """设计否决项：造假信号命中（M2 多项红旗 ≥2）→ 一票否决。"""
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "signals": [
                {"code": "OCF_NP_DIVERGENCE", "severity": "medium", "metric": "ocf_to_np_min",
                 "message": "经营现金流与净利润背离"},
                {"code": "ROE_HIGH", "severity": "medium", "metric": "roe",
                 "message": "ROE 异常偏高"},
            ],
            "handoff": {"quality_score": 60, "risk_signal_codes": ["OCF_NP_DIVERGENCE", "ROE_HIGH"]},
        }, 60),
    }
    r = assess_risk(inputs)
    assert any("造假信号命中" in v for v in r.veto)
    assert r.vetoes[0]["id"] == "V-001"


def test_risk_single_fraud_flag_not_veto():
    """单个造假红旗只是核查信号，不构成否决（避免过度触发）。"""
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "signals": [
                {"code": "ROE_HIGH", "severity": "medium", "metric": "roe",
                 "message": "ROE 异常偏高"},
            ],
            "handoff": {"quality_score": 60, "risk_signal_codes": ["ROE_HIGH"]},
        }, 60),
    }
    r = assess_risk(inputs)
    assert r.veto == []


def test_risk_veto_audit_qualified():
    """设计否决项：审计非标意见（M6 governance_risk_codes AUDIT_QUALIFIED）→ 一票否决。"""
    inputs = {
        "M6_governance": _mod("M6_governance", {
            "handoff": {"governance_score": 70, "governance_risk_codes": [
                {"code": "AUDIT_QUALIFIED", "severity": "high", "description": "审计意见非标"},
            ]},
        }, 70),
    }
    r = assess_risk(inputs)
    assert any("审计非标" in v for v in r.veto)
    # 审计非标只进否决，不进普通风险清单
    assert all(it["source_module"] != "M6_governance" or it["trigger"] != "governance_risk_code=AUDIT_QUALIFIED"
               for it in r.risk_items)


def test_risk_veto_pledge_ratio_gt_80():
    """设计否决项：质押率 > 80%（M6 规则层风险码带 ratio）→ 一票否决。"""
    inputs = {
        "M6_governance": _mod("M6_governance", {
            "handoff": {"governance_score": 70, "governance_risk_codes": [
                {"code": "SHARE_PLEDGE", "severity": "medium", "description": "股权质押", "ratio": 0.85},
            ]},
        }, 70),
    }
    r = assess_risk(inputs)
    assert any("质押率过高" in v for v in r.veto)


def test_risk_pledge_below_threshold_no_veto():
    """质押率未超阈值（或 LLM 无 ratio）→ 只进风险清单，不否决。"""
    for ratio in (0.3, None):
        inputs = {
            "M6_governance": _mod("M6_governance", {
                "handoff": {"governance_score": 70, "governance_risk_codes": [
                    {"code": "SHARE_PLEDGE", "severity": "medium", "description": "股权质押", "ratio": ratio},
                ]},
            }, 70),
        }
        r = assess_risk(inputs)
        assert r.veto == []
        assert any(it["trigger"] == "governance_risk_code=SHARE_PLEDGE" for it in r.risk_items)


def test_risk_veto_industry_decline_high_leverage():
    """设计否决项：行业明确下行 + 高杠杆（M3 prosperity=down 且 M2 资产负债率 ≥60%）。"""
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "metrics": {"debt_to_assets_latest": 0.7},
            "signals": [],
            "handoff": {"quality_score": 55, "risk_signal_codes": []},
        }, 55),
        "M3_growth": _mod("M3_growth", {"handoff": {"prosperity_code": "down"}}),
    }
    r = assess_risk(inputs)
    assert any("高杠杆" in v for v in r.veto)


def test_risk_industry_decline_low_leverage_no_veto():
    """行业下行但杠杆不高 → 只进风险清单，不否决。"""
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "metrics": {"debt_to_assets_latest": 0.3},
            "signals": [],
            "handoff": {"quality_score": 55, "risk_signal_codes": []},
        }, 55),
        "M3_growth": _mod("M3_growth", {"handoff": {"prosperity_code": "down"}}),
    }
    r = assess_risk(inputs)
    assert r.veto == []


def test_risk_items_sorted_by_expected_loss():
    """8.3：风险清单按期望损失（P×L）降序排序，且每项带 expected_loss 字段。"""
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "signals": [
                {"code": "LOSS_YEAR", "severity": "high", "metric": "roe", "message": "存在亏损年份"},
            ],
        }),
        "M3_growth": _mod("M3_growth", {"handoff": {"prosperity_code": "down"}}),
        "M7_market": _mod("M7_market", {"position": "泡沫"}),
        "M8_safety_margin": _mod("M8_safety_margin", {"discount": -0.3}),
    }
    r = assess_risk(inputs)
    assert r.risk_items and all("expected_loss" in it for it in r.risk_items)
    losses = [it["expected_loss"] for it in r.risk_items]
    assert losses == sorted(losses, reverse=True)


def test_risk_max_loss_scenario():
    """压力情景：景气腰斩 + 估值腰斩 → 基于 M8 折扣率估算最大回撤。"""
    inputs = {
        "M8_safety_margin": _mod("M8_safety_margin", {"discount": -0.3}),
        "M7_market": _mod("M7_market", {"position": "泡沫"}),
    }
    r = assess_risk(inputs)
    assert "景气腰斩" in r.max_loss_scenario["scenario"]
    assert r.max_loss_scenario["estimated_downside_pct"] is not None
    assert r.max_loss_scenario["drivers"]
    # 折扣率缺失时定性兜底，不崩溃
    r2 = assess_risk({})
    assert r2.max_loss_scenario["estimated_downside_pct"] is None
    assert "仅定性" in r2.max_loss_scenario["note"]


def test_risk_handoff_contract_fields():
    """契约 handoff：veto_flags（否决 id）/ max_severity / monitor_candidates。"""
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "metrics": {"debt_to_assets_latest": 0.3},
            "signals": [],
            "handoff": {"quality_score": 20, "risk_signal_codes": []},
        }, 20),
        "M7_market": _mod("M7_market", {"position": "泡沫"}),
    }
    r = assess_risk(inputs)
    assert r.veto_flags == ["V-001"] == [v["id"] for v in r.vetoes]
    assert r.max_severity == "critical"  # 有否决 → critical
    assert r.monitor_candidates  # 泡沫 high 进入监控候选
    r2 = assess_risk({})
    assert r2.veto_flags == [] and r2.max_severity == "low" and r2.monitor_candidates == []


def test_shipping_classified_cyclical():
    """航运港口/水运/运输按周期分类（中远海控场景），避免误判资产/成长。"""
    from value_agent.business_model.engine import classify_business_type

    assert classify_business_type("航运港口", 13.0, 15.0, 0.4) == "cyclical"
    assert classify_business_type("水运", 13.0, 15.0, 0.4) == "cyclical"
    assert classify_business_type("高速公路", 15.0, 50.0, 0.4) == "asset_based"


# ---------- backlog 4.x（M3 成长）/ 6.x（M6 治理）/ 7.x（M7）/ 8.x（M9）新增 ----------

def test_growth_scenarios_and_wacc_param():
    """4.4 情景区间 + 4.6 WACC 参数化。"""
    recs = [{"period": f"{2026 - i}1231", "eps": 4.0 * (1.1 ** (9 - i)), "roe": 20,
             "debt_to_assets": 0.3} for i in range(10)]
    r = assess_growth({"records": recs})
    assert r.scenarios["neutral"] == pytest.approx(r.growth_estimate)
    assert r.scenarios["conservative"] <= r.scenarios["neutral"] <= r.scenarios["optimistic"]
    assert r.scenarios["optimistic"] <= 0.20
    r2 = assess_growth({"records": recs}, wacc=0.08)
    assert r2.evidence and any("WACC 8%" in e for e in r2.evidence)


def test_growth_roe_debt_decoupled_from_eps():
    """4.8：最新期缺 EPS 时，ROE/负债率仍进入评分（不再被丢弃）。"""
    recs = [
        {"period": "20251231", "eps": None, "roe": 25, "debt_to_assets": 0.2},
        {"period": "20241231", "eps": 5.0, "roe": 20, "debt_to_assets": 0.3},
        {"period": "20231231", "eps": 4.0, "roe": 18, "debt_to_assets": 0.3},
    ]
    r = assess_growth({"records": recs})
    assert r.growth_estimate > 0
    assert any("再投资质量：ROE 25%" in e for e in r.evidence)  # 最新期 ROE 25 被使用


def test_governance_pledge_ratio_tiering():
    """6.4：质押 >50% 升级 high + 加扣；30% 保持 medium。"""
    from value_agent.governance.engine import assess_governance

    base = {"records": [{"period": f"{y}1231", "cash_div_tax": 2.0} for y in range(2024, 2014, -1)]}
    low = assess_governance(base, events={"records": [
        {"kind": "pledges", "holder": "大股东", "ratio": 0.3},
    ]})
    high = assess_governance(base, events={"records": [
        {"kind": "pledges", "holder": "大股东", "ratio": 0.8},
    ]})
    low_code = next(c for c in low.risk_codes if c["code"] == "SHARE_PLEDGE")
    high_code = next(c for c in high.risk_codes if c["code"] == "SHARE_PLEDGE")
    assert low_code["severity"] == "medium"
    assert high_code["severity"] == "high"
    assert high_code.get("veto_candidate") is True  # 6.5
    assert high.score < low.score  # 高风险加扣


def test_governance_degraded_handoff_neutral():
    """6.7：降级态 handoff.governance_score=50 + DATA_UNAVAILABLE，不再等于 0。"""
    from value_agent.agents.base import AgentContext  # 先加载 agents，避免循环导入
    from value_agent.governance.agent import M6GovernanceAgent

    class _FailData:
        def dividends(self, code):
            raise ConnectionError("boom")

    session = Session(id="s1", company_code="600519", status=SessionStatus.CREATED)
    ctx = AgentContext(session=session, assumptions={}, inputs={}, data=_FailData(), llm=None)
    res = M6GovernanceAgent().run(ctx)
    assert res.outputs["handoff"]["governance_score"] == 50
    assert "DATA_UNAVAILABLE" in res.outputs["handoff"].get("reason_codes", [])


def test_risk_sentiment_heat_upgrades_and_knife():
    """7.15：高估+情绪过热 → severity 升级；低估+过热 → 接飞刀项。"""
    hot = assess_risk({
        "M7_market": _mod("M7_market", {"position": "高估", "sentiment_heat": 0.9}),
    })
    hot_items = [it for it in hot.risk_items if it["category"] == "估值情绪"]
    assert hot_items and hot_items[0]["severity"] == "high"
    knife = assess_risk({
        "M7_market": _mod("M7_market", {"position": "低估", "sentiment_heat": 0.85}),
    })
    assert any(it["category"] == "接飞刀" for it in knife.risk_items)


def test_risk_max_loss_scenario_includes_intrinsic_value():
    """8.5：压力情景输出绝对回撤金额与建议仓位上限（接入 M4 intrinsic/current_price）。"""
    inputs = {
        "M4_valuation": _mod("M4_valuation", {
            "intrinsic_value": {"low": 60, "mid": 100, "high": 140},
            "current_price": 80,
        }),
        "M8_safety_margin": _mod("M8_safety_margin", {"discount": -0.3}),
    }
    r = assess_risk(inputs)
    ml = r.max_loss_scenario
    assert ml.get("estimated_downside_pct") is not None
    assert ml.get("estimated_downside_amount") is not None
    assert ml.get("suggested_position_cap") is not None
    assert ml.get("current_price") == 80


def test_governance_control_event_high_concentration():
    """6.2：前十大股东高度集中 → CONTROL_RISK 低 severity 风险码。"""
    from value_agent.governance.engine import assess_governance

    base = {"records": [{"period": f"{y}1231", "cash_div_tax": 2.0} for y in range(2024, 2014, -1)]}
    r = assess_governance(base, events={"records": [
        {"kind": "control", "event_date": "20260101", "holder": "", "ratio": 0.82,
         "description": "前十大股东合计持股 82%，股权高度集中"},
    ]})
    assert any(c["code"] == "CONTROL_RISK" for c in r.risk_codes)
    assert any("股权集中度" in c["description"] for c in r.risk_codes if c["code"] == "CONTROL_RISK")


def test_growth_cyclical_caps_and_discounts():
    """生产稽核回归（江西铜业/中远海控）：周期特征（ROE 波动 CV>0.3）时
    增速封顶 10% + 评分打折，杜绝景气高点 EPS CAGR 外推成 20% 长期增速。"""
    roe_seq = [3, 22, 5, 25, 4, 26, 6, 24, 5, 23]  # 大幅波动 → CV>0.3
    recs = [
        {"period": f"{2026 - i}1231", "eps": round(2.0 * (1.2 ** (9 - i)), 4),
         "roe": roe_seq[i], "debt_to_assets": 0.4}
        for i in range(10)
    ]
    r = assess_growth({"records": recs})
    assert r.cyclicality_flag is True
    assert r.growth_estimate <= 0.10                    # 封顶 10%
    assert r.scenarios["neutral"] <= 0.10
    assert any("正常化" in e for e in r.evidence)

    stable = [
        {"period": f"{2026 - i}1231", "eps": round(2.0 * (1.2 ** (9 - i)), 4),
         "roe": 22, "debt_to_assets": 0.4}
        for i in range(10)
    ]
    rs = assess_growth({"records": stable})
    assert rs.cyclicality_flag is False
    assert r.score < rs.score                            # 周期成长质量打折


def test_risk_max_severity_is_most_severe():
    """生产稽核回归：max_severity 应取**最严重**等级，不得按编号 max() 取到最轻。

    600362 江西铜业含 medium/high 风险项却报 max_severity=low，M10 仓位风险修正失效。
    """
    inputs = {
        "M2_financial_quality": _mod("M2_financial_quality", {
            "metrics": {"debt_to_assets_latest": 0.3},
            "signals": [
                {"code": "OCF_NP_DIVERGENCE", "severity": "medium", "metric": "ocf_to_np_min",
                 "message": "经营现金流与净利润背离", "evidence": "x"},
                {"code": "LOSS_YEAR", "severity": "high", "metric": "roe",
                 "message": "存在亏损年份", "evidence": "x"},
            ],
            "handoff": {"quality_score": 60, "risk_signal_codes": ["OCF_NP_DIVERGENCE", "LOSS_YEAR"]},
        }, 60),
    }
    r = assess_risk(inputs)
    assert r.max_severity == "high"  # 最严重是 high（此前错误返回 medium/low）
