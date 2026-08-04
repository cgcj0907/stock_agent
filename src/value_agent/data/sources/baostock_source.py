"""BaoStock 数据源：**完全免费**、无积分/token，自带估值历史（peTTM/pbMRQ/psTTM）。

- 覆盖：公司信息、季度财报（利润率/ROE/负债率）、日线行情、估值历史（PE/PB/PS）
- 缺口：无分红接口（分红可后续用 AkShare 巨潮接口补）
- 注意：服务器在国内，海外（Render）连通性需实测；本地开发无问题
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .base import DataSource, to_float

logger = logging.getLogger(__name__)

_K_FIELDS = "date,code,open,high,low,close,volume,peTTM,pbMRQ,psTTM,pcfNcfTTM"


class BaoStockDataSource(DataSource):
    name = "baostock"

    def __init__(self) -> None:
        try:
            import baostock as bs  # 延迟导入
        except ImportError as exc:
            raise ImportError(
                "未安装 baostock：`pip install baostock`（本地免费方案）"
            ) from exc
        self._bs = bs
        lg = bs.login()
        if lg.error_code != "0":
            raise RuntimeError(f"BaoStock 登录失败: {lg.error_msg}")
        self._k_cache: dict[str, tuple[list[dict], list[dict]]] = {}

    # ---- 工具 ----
    def _query(self, fn_name: str, **kwargs) -> list[dict]:
        rs = getattr(self._bs, fn_name)(**kwargs)
        rows: list[dict] = []
        while rs.error_code == "0" and rs.next():
            rows.append(dict(zip(rs.fields, rs.get_row_data())))
        return rows

    # ---- 接口实现 ----
    def company_info(self, code: str) -> dict:
        rows = self._query("query_stock_basic", code=_to_bs_code(code))
        r = rows[0] if rows else {}
        return {
            "code": code,
            "ts_code": r.get("code", _to_bs_code(code)),
            "name": r.get("code_name", code),
            "industry": "",  # BaoStock 无行业字段
            "list_date": (r.get("ipoDate") or "").replace("-", ""),
            "source": self.name,
        }

    def financials(self, code: str, years: int = 10) -> dict:
        bs_code = _to_bs_code(code)
        records: dict[str, dict] = {}
        for year in range(datetime.now().year - years, datetime.now().year + 1):
            for quarter in (1, 2, 3, 4):
                profit = self._query("query_profit_data", code=bs_code, year=year, quarter=quarter)
                balance = self._query("query_balance_data", code=bs_code, year=year, quarter=quarter)
                if not profit:
                    continue
                p, b = profit[0], (balance[0] if balance else {})
                period = (p.get("statDate") or "").replace("-", "")
                if not period:
                    continue
                records[period] = {
                    "period": period,
                    # BaoStock 比率为小数（0.3446=34.46%）→ 转百分比（schema 约定 45.0=45%）
                    "roe": round(to_float(p.get("roeAvg")) * 100, 2) if to_float(p.get("roeAvg")) is not None else None,
                    "grossprofit_margin": round(to_float(p.get("gpMargin")) * 100, 2) if to_float(p.get("gpMargin")) is not None else None,
                    "netprofit_margin": round(to_float(p.get("npMargin")) * 100, 2) if to_float(p.get("npMargin")) is not None else None,
                    # 负债率本身就是小数（0.164=16.4%），schema 约定小数
                    "debt_to_assets": to_float(b.get("liabilityToAsset")),
                    "ocfps": None,  # BaoStock 无直接字段，M2 后续可补
                    "eps": to_float(p.get("epsTTM")),
                    "ocf_to_np": None,
                }
        return {"records": sorted(records.values(), key=lambda r: r["period"]), "source": self.name}

    def _kline(self, code: str) -> tuple[list[dict], list[dict]]:
        """日线 + 估值历史（前复权），带缓存。"""
        if code in self._k_cache:
            return self._k_cache[code]
        start = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
        rows = self._query(
            "query_history_k_data_plus",
            code=_to_bs_code(code),
            fields=_K_FIELDS,
            start_date=start,
            end_date=datetime.now().strftime("%Y-%m-%d"),
            frequency="d",
            adjustflag="2",  # 前复权
        )
        prices: list[dict] = []
        valuations: list[dict] = []
        for r in rows:
            date = r["date"].replace("-", "")
            prices.append(
                {
                    "trade_date": date,
                    "open": to_float(r.get("open")),
                    "close": to_float(r.get("close")),
                    "high": to_float(r.get("high")),
                    "low": to_float(r.get("low")),
                    "volume": to_float(r.get("volume")),
                }
            )
            valuations.append(
                {
                    "trade_date": date,
                    "pe": to_float(r.get("peTTM")),      # BaoStock 只有 TTM PE
                    "pe_ttm": to_float(r.get("peTTM")),
                    "pb": to_float(r.get("pbMRQ")),
                    "ps": to_float(r.get("psTTM")),
                    "dv_ttm": None,                     # 无股息率字段
                    "total_mv": None,
                }
            )
        self._k_cache[code] = (prices, valuations)
        return prices, valuations

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        prices, _ = self._kline(code)
        return {"records": prices, "source": self.name}

    def valuation_history(self, code: str) -> dict:
        _, valuations = self._kline(code)
        return {"records": valuations, "source": self.name}

    def dividends(self, code: str) -> dict:
        # BaoStock 无分红接口；可后续用 AkShare 巨潮分红接口补
        return {"records": [], "source": self.name, "note": "BaoStock 无分红接口"}


def _to_bs_code(code: str) -> str:
    """600519 -> sh.600519；300750 -> sz.300750。"""
    if "." in code:
        return code.lower()
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    return f"sz.{code}"
