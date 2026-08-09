"""M5 真实同行中位数提供器（backlog 5.1）单测：假 akshare 注入。

覆盖：同行中位计算（排除自身）、样本不足回退、板块匹配失败回退、
单只拉取失败跳过、引擎/agent 真实中位接入与静态兜底。
"""
from __future__ import annotations

import datetime

import pandas as pd
import pytest

from value_agent.moat.engine import assess_moat
from value_agent.moat.peer_benchmarks import PeerBenchmarkProvider


@pytest.fixture(autouse=True)
def _clear_peer_cache():
    """模块级 _CACHE 跨测试残留会导致假 akshare 结果串测：每个测试前清空。"""
    from value_agent.moat.peer_benchmarks import _CACHE

    _CACHE.clear()
    yield


class _FakeAk:
    """假 akshare：固定行业/板块/成分股/财务指标，供 provider 单测（不联网）。"""

    def __init__(self, industry="保险", boards=None, cons=None, financials=None, fail=None):
        self.industry = industry
        self.boards = boards or ["保险", "银行", "证券"]
        self.cons = cons or {"保险": ["601318", "601628", "601601", "601336", "600291", "601319"]}
        self.financials = financials or {}
        self.fail = set(fail or [])

    def stock_individual_info_em(self, symbol):
        return pd.DataFrame({"item": ["股票代码", "行业"], "value": [symbol, self.industry]})

    def stock_board_industry_name_em(self):
        return pd.DataFrame({"板块名称": self.boards})

    def stock_board_industry_cons_em(self, symbol):
        return pd.DataFrame({"代码": self.cons[symbol]})

    def stock_financial_analysis_indicator(self, symbol, start_year="1900"):
        if symbol in self.fail:
            raise ConnectionError("network down")
        rows = self.financials.get(symbol)
        if not rows:
            raise ValueError("no data")
        if isinstance(rows, dict):
            rows = [rows]  # 兼容单行
        return pd.DataFrame(rows)


def _fin(roe, np_, debt, gm=None):
    return {"日期": datetime.date(2024, 12, 31), "净资产收益率(%)": roe,
            "销售毛利率(%)": gm, "销售净利率(%)": np_, "资产负债率(%)": debt}


def _insurance_financials():
    # 601318 是自身，其余 5 家为同行：ROE 12/10/14/8/11 → 中位 11；净利率 8/6/9/5/7 → 7
    return {
        "601318": _fin(20.0, 15.0, 0.88),
        "601628": _fin(12.0, 8.0, 0.90),
        "601601": _fin(10.0, 6.0, 0.88),
        "601336": _fin(14.0, 9.0, 0.92),
        "600291": _fin(8.0, 5.0, 0.85),
        "601319": _fin(11.0, 7.0, 0.90),
    }


def test_medians_computes_peer_median_excluding_self():
    fake = _FakeAk(financials=_insurance_financials())
    med = PeerBenchmarkProvider(ak=fake).medians("601318", "保险")
    assert med is not None
    assert med.benchmark == "保险"
    assert med.peer_count == 5          # 排除自身 601318
    assert med.roe_median == 11.0
    assert med.np_median == 7.0
    assert med.debt_median == 0.90
    assert med.gm_median is None        # 保险公司无毛利率口径
    assert med.period == "2024-12-31"
    assert any("真实动态" in e for e in med.evidence)


def test_medians_too_few_peers_returns_none():
    fin = {c: _fin(10.0, 6.0, 0.9) for c in ("601628", "601601")}  # 仅 2 家有数据
    fake = _FakeAk(financials=fin)
    assert PeerBenchmarkProvider(ak=fake).medians("601318", "保险") is None


def test_medians_no_board_match_returns_none():
    fake = _FakeAk(industry="未知行业", boards=["保险", "银行", "证券"], financials=_insurance_financials())
    assert PeerBenchmarkProvider(ak=fake).medians("601318", "未知行业") is None


def test_medians_skips_failed_peer():
    fin = _insurance_financials()
    fake = _FakeAk(financials=fin, fail={"601628"})  # 601628 拉取失败 → 跳过
    med = PeerBenchmarkProvider(ak=fake).medians("601318", "保险")
    assert med is not None
    assert med.peer_count == 4                     # 601628 失败跳过，剩 4 家
    assert med.roe_median == 10.5                  # [10,14,8,11] → 中位 (10+11)/2=10.5


def test_medians_respects_total_budget_on_hanging_peers():
    """慢网加固：成分股财务接口挂起时不卡死主流程，预算内回退（返回 None）。"""
    import time as _time

    class _SlowAk(_FakeAk):
        def stock_financial_analysis_indicator(self, symbol, start_year="1900"):
            _time.sleep(1.2)  # 每只挂 1.2s（5 只并行也要 >1.2s）
            return super().stock_financial_analysis_indicator(symbol, start_year)

    fake = _SlowAk(financials=_insurance_financials())
    p = PeerBenchmarkProvider(ak=fake, total_budget=0.3)  # 0.3s 总预算
    t0 = _time.time()
    med = p.medians("601318", "保险")
    elapsed = _time.time() - t0
    assert med is None          # 预算内收不齐 ≥3 家 → 回退静态基准
    assert elapsed < 2.0        # 不被挂起卡死（远小于 5×1.2s）


def test_medians_caches_result():
    fake = _FakeAk(financials=_insurance_financials())
    p = PeerBenchmarkProvider(ak=fake)
    first = p.medians("601318", "保险")
    second = p.medians("601318", "保险")
    assert first is second  # 进程内缓存命中


# ---------- 引擎 / agent 集成 ----------

def test_engine_uses_real_peer_medians():
    fin = {"records": [{"period": f"{2026 - i}1231", "roe": 15.0,
                        "grossprofit_margin": 50.0, "debt_to_assets": 0.3} for i in range(10)]}
    med = {"roe_median": 12.0, "gm_median": 40.0, "debt_median": 0.4,
           "peer_count": 10, "period": "2024-12-31"}
    r = assess_moat(fin, industry="白酒", peer_medians=med)
    assert r.peer is not None
    assert r.peer.roe_median == 12.0      # 真实中位覆盖静态（白酒 20）
    assert r.peer.margin_median == 40.0   # 白酒用毛利率口径
    assert any("真实动态" in e for e in r.evidence)


def test_engine_uses_np_median_for_financial():
    fin = {"records": [{"period": f"{2026 - i}1231", "roe": 13.5, "netprofit_margin": 15.1,
                        "grossprofit_margin": None, "debt_to_assets": None} for i in range(10)]}
    med = {"roe_median": 10.0, "np_median": 12.0, "peer_count": 6, "period": "2024-12-31"}
    r = assess_moat(fin, industry="保险", peer_medians=med)
    assert r.peer.margin_median == 12.0   # 金融走净利率口径


def test_agent_uses_real_peer_medians(monkeypatch):
    from tests.conftest import StubData
    from value_agent.agents.base import AgentContext
    from value_agent.moat.agent import M5MoatAgent
    from value_agent.sessions.models import Session, SessionStatus

    monkeypatch.setattr(
        "value_agent.moat.agent._fetch_peer_medians",
        lambda code, industry: {
            "roe_median": 22.0, "gm_median": 75.0, "debt_median": 0.30,
            "peer_count": 8, "period": "2024-12-31",
        },
    )
    sess = Session(id="s", company_code="600519", company_name="贵州茅台", status=SessionStatus.CREATED)
    ctx = AgentContext(session=sess, assumptions={}, inputs={}, data=StubData(), llm=None)
    res = M5MoatAgent().run(ctx)
    peer = res.outputs["rule_proxy"]["peer"]
    assert peer["roe_median"] == 22.0
    assert peer["margin_median"] == 75.0
    assert any("真实动态" in e for e in res.evidence)


def test_agent_falls_back_to_static_when_peer_none(monkeypatch):
    """真实中位返回 None（无网/失败）→ 引擎用静态细分基准，链路不阻断。"""
    from tests.conftest import StubData
    from value_agent.agents.base import AgentContext
    from value_agent.moat.agent import M5MoatAgent
    from value_agent.sessions.models import Session, SessionStatus

    monkeypatch.setattr(
        "value_agent.moat.agent._fetch_peer_medians", lambda code, industry: None
    )
    sess = Session(id="s", company_code="600519", company_name="贵州茅台", status=SessionStatus.CREATED)
    ctx = AgentContext(session=sess, assumptions={}, inputs={}, data=StubData(), llm=None)
    res = M5MoatAgent().run(ctx)
    assert res.outputs["rule_proxy"]["peer"]["benchmark"] == "liquor"  # 静态细分兜底
    assert res.outputs["width"] == "窄"
    assert not any("真实动态" in e for e in res.evidence)


# ---------- 2026-08-09：周期行业同行侧跨周期均值中位（时间口径对齐） ----------

def _roe_series(roe_list: list[float]) -> list[dict]:
    """生成近 N 年单指标年报行（ROE 波动，模拟周期股同行）。"""
    rows = []
    for i, roe in enumerate(roe_list):
        rows.append({
            "日期": datetime.date(2024 - i, 12, 31),
            "净资产收益率(%)": roe,
            "销售净利率(%)": 5.0,
            "资产负债率(%)": 0.5,
        })
    return rows


def test_medians_computes_cross_cycle_median():
    """周期行业：同行侧同时给出最新中位与跨周期均值中位（roe_median_cycle）。"""
    fin = {
        "601318": _roe_series([20.0] * 8),              # 自身，排除
        "601628": _roe_series([12, 10, 8, 6, 4, 6, 8, 10]),    # 均值 8
        "601601": _roe_series([16, 14, 12, 10, 8, 10, 12, 14]),  # 均值 12
        "601336": _roe_series([10, 8, 6, 4, 2, 4, 6, 8]),      # 均值 6
    }
    fake = _FakeAk(financials=fin)
    med = PeerBenchmarkProvider(ak=fake).medians("601318", "保险")
    assert med is not None
    assert med.peer_count == 3
    assert med.roe_median == 10.0        # 最新期 [10, 14, 8] 中位 10
    assert med.roe_median_cycle == 8.0   # 跨周期均值 [8, 12, 6] 中位 8
    assert med.cycle_window == 8


def test_engine_uses_peer_cycle_median_for_cyclical():
    """周期行业：公司用 8 年跨周期均值，同行基准也取跨周期均值中位（同口径）。

    回归：此前同行只用最新期（roe_median），周期高点/低点系统性高/低估公司护城河。
    """
    fin = {"records": [
        {"period": f"{2026 - i}1231", "roe": 12.0 if i % 2 == 0 else 4.0,
         "grossprofit_margin": 20.0, "debt_to_assets": 0.5}
        for i in range(10)
    ]}  # 公司 8 年跨周期均值 = 8.0
    med = {"roe_median": 5.0, "roe_median_cycle": 8.0, "peer_count": 6, "period": "2024-12-31"}
    r = assess_moat(fin, industry="铜", business_type="cyclical", peer_medians=med)
    assert r.peer is not None
    assert r.peer.roe_median == 8.0   # 周期股用跨周期中位，而非最新中位 5.0
    assert any("跨周期均值中位" in e for e in r.evidence)
    assert any("同行跨周期中位" in s for s in r.signals)
