"""M2 分行业口径（backlog 12.1）：金融/保险/银行按行业规则评估，避免误判一票否决。

背景：中国平安案例——保险公司净利润主要由投资端决定、经营现金流含保费/赔付/准备金
变动，OCF/NP<0.8 或负债率 90%+ 都是行业常态；旧逻辑会把 M2 打到 <30 触发一票否决，
与 2024/2025 年报（OCF/NP 3.0/4.9、ROE 14%）明显矛盾。
"""
import pytest

from value_agent.financials.quality import (
    DEFAULT_PROFILE,
    FinancialProfile,
    _load_financial_routing,
    analyze_financial_quality,
    resolve_profile,
)


def _rec(period, roe=12.0, ocf_to_np=1.2, debt=0.90, eps=5.0, ocfps=6.0):
    return {
        "period": period,
        "roe": roe,
        "grossprofit_margin": 45.0,
        "netprofit_margin": 15.0,
        "debt_to_assets": debt,
        "ocfps": ocfps,
        "eps": eps,
        "ocf_to_np": ocf_to_np,
    }


def _insurance_records():
    """保险典型：年度 OCF/NP 除 2021 外都健康，季度数据有强季节性噪音（0.15）。"""
    recs = []
    annual = [
        ("20251231", 3.5), ("20241231", 2.8), ("20231231", 3.6),
        ("20221231", 4.8), ("20211231", 0.74), ("20201231", 2.2),
    ]
    for period, ratio in annual:
        recs.append(_rec(period, ocf_to_np=ratio))
    # 季度噪音：Q1/Q3 现金流比低（保费/赔付季节性），若被纳入 min 会误触发
    recs.append(_rec("20260331", ocf_to_np=0.15))
    recs.append(_rec("20250930", ocf_to_np=0.20))
    return recs


def test_insurance_high_debt_and_quarterly_noise_not_vetoed():
    """金融/保险口径：季度噪音被排除、高杠杆按常态 → 不再误触发 OCF_NP_DIVERGENCE。"""
    recs = _insurance_records()
    r = analyze_financial_quality(recs, business_type="financial", financial_subtype="insurance")
    codes = {sig.code for sig in r.signals}
    assert "OCF_NP_DIVERGENCE" not in codes, r.signals
    assert r.score >= 60, (r.score, r.evidence)
    # 杠杆按行业常态：不再出现"杠杆过高"
    lever_notes = [s for s in r.details["杠杆"]]
    assert any("行业高杠杆属常态" in s for s in lever_notes)
    # 年报口径：季度 0.15 不进入 min（否则 min=0.15 会触发）
    assert r.metrics["ocf_to_np_min"] >= 0.5, r.metrics


def test_same_data_under_standard_profile_still_triggers():
    """通用口径（M1 缺失/制造业）：季度噪音+高杠杆 → 命中 OCF_NP_DIVERGENCE 且杠杆扣分。"""
    recs = _insurance_records()
    r = analyze_financial_quality(recs)  # 无 business_type → 默认通用口径
    assert r.profile == DEFAULT_PROFILE
    codes = {sig.code for sig in r.signals}
    assert "OCF_NP_DIVERGENCE" in codes
    sig = next(s for s in r.signals if s.code == "OCF_NP_DIVERGENCE")
    assert sig.severity == "medium"
    assert any("杠杆过高" in s for s in r.details["杠杆"])


def _cm_records_with_quarterly_noise():
    """消费垄断（如家电制造）：年报 OCF/NP 健康，Q1/Q3 有季节性噪音。"""
    recs = [_rec(f"{y}1231", ocf_to_np=1.2) for y in range(2026, 2016, -1)]
    recs.append(_rec("20260331", ocf_to_np=0.40))
    recs.append(_rec("20250930", ocf_to_np=0.55))
    return recs


def test_consumer_monopoly_annual_only_ignores_quarterly_noise():
    """v2.2：消费垄断（家电制造）现金流比仅用年报——季度季节性不误触发 OCF_NP_DIVERGENCE。"""
    recs = _cm_records_with_quarterly_noise()
    r = analyze_financial_quality(recs, business_type="consumer_monopoly")
    codes = {sig.code for sig in r.signals}
    assert "OCF_NP_DIVERGENCE" not in codes, r.signals
    assert r.metrics["ocf_to_np_min"] >= 1.0  # 仅年报口径
    # 标签不再是误导性的"金融口径"
    assert not any("金融口径" in s for s in r.details["现金流"])


def test_consumer_monopoly_quarterly_noise_triggers_under_all_periods():
    """对照：若现金流比用全部期（含季度），家电制造会被季度季节性误触发。"""
    recs = _cm_records_with_quarterly_noise()
    r = analyze_financial_quality(recs)  # 无 business_type → 通用口径（全部期）
    codes = {sig.code for sig in r.signals}
    assert "OCF_NP_DIVERGENCE" in codes
    assert r.metrics["ocf_to_np_min"] == pytest.approx(0.40)


def test_cyclical_cashflow_label_not_financial():
    """v2.2：周期行业 lenient 文案显示'周期口径'而非'金融口径'。"""
    recs = [_rec(f"{y}1231", ocf_to_np=1.2) for y in range(2026, 2016, -1)]
    r = analyze_financial_quality(recs, business_type="cyclical")
    assert not any("金融口径" in s for s in r.details["现金流"])
    assert any("周期口径" in s for s in r.details["现金流"])


def test_bad_insurance_still_flagged_low_severity():
    """金融口径下真正差的现金流（年度 min<0.5）仍出低severity信号，不因行业豁免而漏报。"""
    recs = [_rec(f"{y}1231", ocf_to_np=0.2) for y in range(2026, 2016, -1)]
    r = analyze_financial_quality(recs, business_type="financial", financial_subtype="insurance")
    sig = next((s for s in r.signals if s.code == "OCF_NP_DIVERGENCE"), None)
    assert sig is not None
    assert sig.severity == "low"  # 行业豁免 ≠ 漏报：严重度降为 low，仍提示
    assert any("显著偏低" in s for s in r.details["现金流"])


def test_bank_profile_also_industry_leverage():
    """银行同样属于金融行业口径（负债率高是常态，不按杠杆过高扣分）。"""
    recs = [_rec(f"{y}1231", debt=0.92, ocf_to_np=1.5) for y in range(2026, 2016, -1)]
    r = analyze_financial_quality(recs, business_type="financial", financial_subtype="bank")
    assert any("行业高杠杆属常态" in s for s in r.details["杠杆"])
    assert r.score >= 60


def test_resolve_profile_precedence():
    """优先级：financial_subtype 配置 > business_type > default > 代码默认。"""
    assert resolve_profile() == DEFAULT_PROFILE
    assert resolve_profile("financial").cashflow_mode == "lenient"
    assert resolve_profile("financial", "insurance").cashflow_annual_only is True
    # 消费垄断：标准阈值（0.8）但仅年报（v2.2，防家电等制造型季度季节性误报）
    cm = resolve_profile("consumer_monopoly")
    assert cm.cashflow_mode == "standard"
    assert cm.cashflow_threshold == 0.8
    assert cm.cashflow_annual_only is True
    assert cm.leverage_mode == "standard"


def test_routing_config_matches_code_defaults():
    """config/financial_routing.yaml 是唯一事实来源；代码兜底与 default 一致，防漂移。"""
    routing = _load_financial_routing()
    assert routing, "financial_routing.yaml 应可解析"
    # 六个生意类型全覆盖（对齐 M4 路由表）
    assert {"consumer_monopoly", "growth", "cyclical", "financial",
            "asset_based", "stable_dividend"} <= set(routing)

    default_cfg = routing.get("default", {})
    prof = FinancialProfile(**default_cfg) if default_cfg else DEFAULT_PROFILE
    assert prof == DEFAULT_PROFILE, "YAML default 与代码默认漂移"

    # 关键行业口径锁定
    assert routing["financial"]["cashflow_mode"] == "lenient"
    assert routing["financial"]["cashflow_annual_only"] is True
    assert routing["financial"]["cashflow_threshold"] == 0.5
    assert routing["financial"]["leverage_mode"] == "industry"
    assert routing["financial"]["ocf_divergence_severity"] == "low"
    assert routing["bank"]["cashflow_mode"] == "skip"
    assert routing["cyclical"]["cashflow_threshold"] == 0.4
    assert routing["cyclical"]["leverage_mode"] == "standard"
    assert routing["growth"]["cashflow_threshold"] == 0.6


# ---------- 12.1 全量生意类型路由（对齐 M4）----------

def test_cyclical_low_cash_tolerated_within_threshold():
    """周期股底部 OCF/NP 天然偏低：0.45（>0.4 阈值）不触发信号，杠杆仍按标准扣分。"""
    recs = [_rec(f"{y}1231", ocf_to_np=0.45, debt=0.70) for y in range(2026, 2016, -1)]
    r = analyze_financial_quality(recs, business_type="cyclical")
    codes = {sig.code for sig in r.signals}
    assert "OCF_NP_DIVERGENCE" not in codes, r.signals
    assert any("杠杆偏高" in s for s in r.details["杠杆"])  # 杠杆不因行业放宽


def test_cyclical_bad_cash_still_flagged_medium():
    """周期股现金流真的很差（min<0.4）仍出 medium 信号（现金流对周期股同样重要）。"""
    recs = [_rec(f"{y}1231", ocf_to_np=0.2, debt=0.60) for y in range(2026, 2016, -1)]
    r = analyze_financial_quality(recs, business_type="cyclical")
    sig = next((s for s in r.signals if s.code == "OCF_NP_DIVERGENCE"), None)
    assert sig is not None
    assert sig.severity == "medium"


def test_growth_lenient_threshold():
    """成长股：min 0.65（≥0.6 成长阈值）不触发，通用口径 0.65<0.8 会触发。"""
    recs = [_rec(f"{y}1231", ocf_to_np=0.65, debt=0.45) for y in range(2026, 2016, -1)]
    r_growth = analyze_financial_quality(recs, business_type="growth")
    assert "OCF_NP_DIVERGENCE" not in {s.code for s in r_growth.signals}
    r_default = analyze_financial_quality(recs)  # 通用口径仍会触发
    assert "OCF_NP_DIVERGENCE" in {s.code for s in r_default.signals}


def test_bank_cashflow_skip_neutral():
    """银行：OCF/NP 无判别力 → skip 中性，不因缺现金流数据/比值低出信号。"""
    recs = [_rec(f"{y}1231", ocf_to_np=None, ocfps=None, eps=1.5, debt=0.92)
            for y in range(2026, 2016, -1)]
    r = analyze_financial_quality(recs, business_type="financial", financial_subtype="bank")
    codes = {sig.code for sig in r.signals}
    assert "OCF_NP_DIVERGENCE" not in codes
    assert "CASHFLOW_MISSING" not in codes  # skip 模式不再把"缺现金流"当风险
    assert any("行业高杠杆属常态" in s for s in r.details["杠杆"])
    assert any("按中性计" in s for s in r.details["现金流"])


def test_all_business_types_resolve_without_error():
    """六个生意类型都能解析出合法 profile（防新增类型漏配置）。"""
    for bt in ("consumer_monopoly", "growth", "cyclical", "financial",
               "asset_based", "stable_dividend"):
        p = resolve_profile(bt)
        assert p.cashflow_mode in ("standard", "lenient", "skip")
        assert p.leverage_mode in ("standard", "industry")
        assert 0 < p.cashflow_threshold <= 1
