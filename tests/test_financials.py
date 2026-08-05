"""M2 财务质量引擎单元测试：优质/劣质/缺失数据。"""
import pytest

from value_agent.financials.quality import analyze_financial_quality


def _records(roe_list, ocf_to_np_list, debt_list, **kw):
    recs = []
    for i in range(len(roe_list)):
        year = 2026 - i
        rec = {
            "period": f"{year}1231",
            "roe": roe_list[i],
            "grossprofit_margin": kw.get("gp", 45.0),
            "netprofit_margin": kw.get("np", 25.0),
            "debt_to_assets": debt_list[i],
            "ocfps": kw.get("ocfps"),
            "eps": kw.get("eps"),
            "ocf_to_np": ocf_to_np_list[i] if i < len(ocf_to_np_list) else None,
        }
        recs.append(rec)
    return recs


def test_excellent_company_scores_high():
    recs = _records([18] * 10, [1.2] * 10, [0.35] * 10)
    r = analyze_financial_quality(recs)
    assert r.score >= 90
    assert r.signals == []


def test_loss_and_cashflow_problems_trigger_signals():
    recs = _records([-5, 12, 8, 15, 14, 13, 12, 15, 16, 17], [0.5, 0.9, 1.1, 1.2, 1.1, 1.0, 1.0, 1.1, 1.2, 1.3], [0.75] * 10)
    r = analyze_financial_quality(recs)
    assert any("背离" in s for s in r.signals)
    assert any("亏损" in s for s in r.signals)
    assert r.score < 60


def test_high_leverage_scores_low():
    recs = _records([18] * 10, [1.2] * 10, [0.85] * 10)
    r = analyze_financial_quality(recs)
    notes = [
        s for v in r.details.values() for s in (v if isinstance(v, list) else [v])
    ]
    assert any("杠杆" in s for s in notes)
    assert r.score < 90


def test_missing_cashflow_is_neutral_not_fatal():
    recs = _records([18] * 10, [], [0.35] * 10, ocfps=None, eps=None)
    r = analyze_financial_quality(recs)
    assert r.score >= 70  # 现金流按中性计，不致命


def test_roe_jump_signal():
    recs = _records([30, 12, 15, 16, 15, 14, 15, 16, 15, 16], [1.2] * 10, [0.35] * 10)
    r = analyze_financial_quality(recs)
    assert any("突变" in s for s in r.signals)
