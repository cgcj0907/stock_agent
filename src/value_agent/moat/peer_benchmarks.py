"""M5 真实同行中位数提供器：AkShare 行业成分股财务指标 → 同行中位（backlog 5.1）。

静态 INDUSTRY_SEGMENT_BENCHMARKS / PEER_BENCHMARKS 只是兜底；本提供器给出真实同行中位数：
  个股行业（stock_individual_info_em）
  → 东财行业板块（stock_board_industry_name_em，名称匹配）
  → 成分股（stock_board_industry_cons_em，排除自身、上限 _MAX_PEERS）
  → 每只成分股财务指标（stock_financial_analysis_indicator，最新年报）
  → ROE/毛利率/净利率/资产负债率 同行中位数。

任何一步失败 / 超时 / 样本不足（< _MIN_PEERS）→ 返回 None，调用方回退静态基准，
绝不阻塞分析主流程。进程内缓存 TTL（同 CompanyReferences 模式）。
"""
from __future__ import annotations

import logging
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as _FutTimeout
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, PeerMedians | None]] = {}
_CACHE_TTL = 6 * 3600      # 6 小时
_MAX_PEERS = 15            # 财务指标拉取上限（避免大板块拉上百只）
_MIN_PEERS = 3             # 少于 3 家成功样本 → 不算同行中位
_CALL_TIMEOUT = 5.0        # 单次 akshare 调用超时（防慢网挂死主流程）
_TOTAL_BUDGET = 25.0       # 单次 medians() 总预算（超时即放弃，回退静态基准）
_MAX_WORKERS = 4           # 成分股财务指标并行拉取线程数
_ANNUAL_MONTH_DAY = (12, 31)  # 年报口径（过滤 1231 期）

# 新浪财务指标列名（按子串匹配，兼容口径差异）
_ROE_COLS = ("净资产收益率",)
_GM_COLS = ("销售毛利率",)
_NP_COLS = ("销售净利率",)
_DEBT_COLS = ("资产负债率",)


@dataclass
class PeerMedians:
    """真实同行中位数结果（供 assess_moat peer_medians 参数消费）。"""

    benchmark: str                 # 东财行业板块名
    period: str                    # 年报期（如 2024-12-31）
    roe_median: float | None
    gm_median: float | None        # 毛利率口径
    np_median: float | None        # 净利率口径（金融用）
    debt_median: float | None
    peer_count: int                # 成功拉取并参与中位数的公司数
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "benchmark": self.benchmark,
            "period": self.period,
            "roe_median": self.roe_median,
            "gm_median": self.gm_median,
            "np_median": self.np_median,
            "debt_median": self.debt_median,
            "peer_count": self.peer_count,
        }


_EXECUTOR = ThreadPoolExecutor(
    max_workers=_MAX_WORKERS, thread_name_prefix="moat-peer"
)


def _call(deadline: float, fn, *args, timeout: float = _CALL_TIMEOUT, **kwargs):
    """在线程里执行单次 akshare 调用，带单次超时 + 总预算（防慢网挂死主流程）。"""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("同行中位拉取总预算耗尽")
    fut = _EXECUTOR.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=min(timeout, remaining))
    except _FutTimeout:
        raise TimeoutError(f"akshare 调用超时（>{min(timeout, remaining):.1f}s）")


def _not_na(v: Any) -> bool:
    """非空且非 NaN（NaN != NaN 的判空在 lint 里易误报，改用 math.isnan）。"""
    if v is None:
        return False
    if isinstance(v, float):
        return not math.isnan(v)
    return True


class PeerBenchmarkProvider:
    """真实同行中位数（AkShare）。进程内缓存 TTL；任何失败返回 None。"""

    def __init__(self, ak=None, total_budget: float | None = None) -> None:
        self._ak = ak  # 测试可注入假 akshare
        self._total_budget = total_budget if total_budget is not None else _TOTAL_BUDGET
        self._boards: list[str] | None = None

    def _akshare(self):
        if self._ak is None:
            try:
                import akshare as ak
            except ImportError as exc:
                raise ImportError("未安装 akshare：`pip install akshare`（本地免费方案）") from exc
            self._ak = ak
        return self._ak

    # ---- 对外入口 ----
    def medians(self, code: str, industry: str = "") -> PeerMedians | None:
        cached = _CACHE.get(code)
        if cached is not None and time.monotonic() - cached[0] <= _CACHE_TTL:
            return cached[1]
        try:
            result = self._compute(code, industry)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[peer] %s 同行中位拉取失败（%s），回退静态基准", code, type(exc).__name__)
            result = None
        if len(_CACHE) >= 256:
            _CACHE.clear()
        _CACHE[code] = (time.monotonic(), result)
        return result

    # ---- 内部步骤（均可被单测注入假 akshare 覆盖）----
    def _compute(self, code: str, industry: str) -> PeerMedians | None:
        deadline = time.monotonic() + self._total_budget
        ak = self._akshare()
        ind = self._industry(ak, code, deadline) or (industry or "")
        if not ind:
            return None
        board = self._match_board(ak, ind, deadline)
        if board is None:
            logger.warning("[peer] %s 行业「%s」未匹配到东财行业板块，回退静态基准", code, ind)
            return None
        peers = [c for c in self._constituents(ak, board, deadline) if c != code][:_MAX_PEERS]
        if len(peers) < _MIN_PEERS:
            return None
        # 成分股财务指标：小并发拉取，受总预算约束（任一超时即放弃已得部分）
        rows: list[dict] = []
        pending = {
            _EXECUTOR.submit(self._latest_annual, ak, c, deadline): c
            for c in peers
        }
        remaining = deadline - time.monotonic()
        try:
            for fut in as_completed(pending, timeout=max(0.1, remaining)):
                c = pending[fut]
                try:
                    rows.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[peer] %s 财务指标拉取失败（%s），跳过", c, type(exc).__name__)
        except _FutTimeout:
            logger.warning("[peer] %s 成分股财务指标拉取超时（已得 %d/%d），用已得样本", code, len(rows), len(peers))
        if len(rows) < _MIN_PEERS:
            return None
        med = self._medians(rows, board)
        med.evidence = [
            f"同行中位：真实动态（{board}，{med.peer_count} 家，{med.period}）"
        ]
        return med

    @staticmethod
    def _industry(ak, code: str, deadline: float | None = None) -> str:
        df = _call(deadline or time.monotonic() + _CALL_TIMEOUT, ak.stock_individual_info_em, code)
        if df is None or getattr(df, "empty", True) or "item" not in df.columns:
            return ""
        for _, row in df.iterrows():
            if str(row.get("item") or "").strip() == "行业":
                return str(row.get("value") or "").strip()
        return ""

    @staticmethod
    def _match_board(ak, industry: str, deadline: float | None = None) -> str | None:
        df = _call(deadline or time.monotonic() + _CALL_TIMEOUT, ak.stock_board_industry_name_em)
        if df is None or getattr(df, "empty", True) or "板块名称" not in df.columns:
            return None
        names = [str(x).strip() for x in df["板块名称"].tolist() if str(x).strip() and str(x).strip() != "nan"]
        if industry in names:
            return industry
        for n in names:  # 包含匹配（板块「家电行业」⊇ 行业「家电」）
            if industry in n or n in industry:
                return n
        return None

    @staticmethod
    def _constituents(ak, board: str, deadline: float | None = None) -> list[str]:
        df = _call(deadline or time.monotonic() + _CALL_TIMEOUT, ak.stock_board_industry_cons_em, board)
        if df is None or getattr(df, "empty", True) or "代码" not in df.columns:
            return []
        return [
            str(x).strip()
            for x in df["代码"].tolist()
            if str(x).strip() and str(x).strip() != "nan"
        ]

    @staticmethod
    def _latest_annual(ak, code: str, deadline: float | None = None) -> dict:
        # 注意：本方法在并行段的工作线程里运行，直接调 ak（不嵌套 _call 提交到同一
        # _EXECUTOR，否则 4 个 worker 被外层占住会死锁）；超时由外层 as_completed
        # 的总预算兜底——单只挂起只浪费一个 worker，不影响整体回退。
        df = ak.stock_financial_analysis_indicator(symbol=code, start_year="1900")
        if df is None or getattr(df, "empty", True) or "日期" not in df.columns:
            raise ValueError("no financial data")
        recs = df.to_dict("records")
        annual = [r for r in recs if _is_annual(r.get("日期"))]
        if not annual:
            annual = recs
        latest = annual[-1]  # akshare 已按日期升序

        def col(prefixes: tuple[str, ...]) -> float | None:
            for p in prefixes:
                for k, v in latest.items():
                    if p in str(k) and _not_na(v):
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            continue
            return None

        return {
            "roe": col(_ROE_COLS),
            "gm": col(_GM_COLS),
            "np": col(_NP_COLS),
            "debt": col(_DEBT_COLS),
            "period": str(latest.get("日期")),
        }

    @staticmethod
    def _medians(rows: list[dict], board: str) -> PeerMedians:
        def med(key: str) -> float | None:
            vals = sorted(r[key] for r in rows if r.get(key) is not None)
            return round(statistics.median(vals), 2) if vals else None

        return PeerMedians(
            benchmark=board,
            period=rows[0]["period"],
            roe_median=med("roe"),
            gm_median=med("gm"),
            np_median=med("np"),
            debt_median=med("debt"),
            peer_count=len(rows),
        )


def _is_annual(d: Any) -> bool:
    """日期是年报（12-31）；兼容 datetime.date / str / None。"""
    if d is None:
        return False
    s = str(d)
    return s.endswith(("12-31", "1231", "12/31"))
