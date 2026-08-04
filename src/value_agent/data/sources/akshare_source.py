"""AkShare 数据源（新浪/东财/乐咕乐股，全免费、无 token）。

- 覆盖最全：公司信息（含行业）、财务指标、前复权日线、
  估值历史（乐咕乐股 pe/pb/ps/股息率，10 年）、分红（巨潮）
- 风险：抓取东财/新浪公开接口，**海外 IP（Render）可能被限流/超时**，
  用 `python -m value_agent data ping` 实测；本地开发 100% 可用
"""
from __future__ import annotations

import logging

from .base import DataSource, to_float

logger = logging.getLogger(__name__)


class AkShareDataSource(DataSource):
    name = "akshare"

    def __init__(self) -> None:
        try:
            import akshare as ak  # 延迟导入
        except ImportError as exc:
            raise ImportError(
                "未安装 akshare：`pip install akshare`（本地免费方案）"
            ) from exc
        self._ak = ak

    def company_info(self, code: str) -> dict:
        df = self._ak.stock_individual_info_em(symbol=code)
        kv = dict(zip(df["item"], df["value"]))
        return {
            "code": code,
            "ts_code": code,
            "name": str(kv.get("股票简称", code)),
            "industry": str(kv.get("行业", "")),
            "list_date": str(kv.get("上市时间", "") or ""),
            "source": self.name,
        }

    def financials(self, code: str, years: int = 10) -> dict:
        df = self._ak.stock_financial_analysis_indicator(symbol=code)
        # 列名（新浪）：日期, 净资产收益率(%), 毛利率(%), 净利率(%), 资产负债率(%), 每股收益, 每股经营现金流
        records: list[dict] = []
        for _, r in df.head(years * 4).iterrows():
            period = str(r.get("日期", "") or "")
            if not period or period in ("nan", "-"):
                continue
            records.append(
                {
                    "period": period.replace("-", ""),
                    "roe": to_float(r.get("净资产收益率(%)")),
                    "grossprofit_margin": to_float(r.get("毛利率(%)")),
                    "netprofit_margin": to_float(r.get("净利率(%)")),
                    "debt_to_assets": to_float(r.get("资产负债率(%)"), 100.0),  # % → 小数
                    "ocfps": to_float(r.get("每股经营现金流")),
                    "eps": to_float(r.get("每股收益")),
                    "ocf_to_np": None,
                }
            )
        return {"records": records, "source": self.name}

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        df = self._ak.stock_zh_a_hist(
            symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq"
        )
        records = [
            {
                "trade_date": str(r["日期"]).replace("-", ""),
                "open": to_float(r.get("开盘")),
                "close": to_float(r.get("收盘")),
                "high": to_float(r.get("最高")),
                "low": to_float(r.get("最低")),
                "volume": to_float(r.get("成交量")),  # 单位：手
            }
            for _, r in df.iterrows()
        ]
        return {"records": records, "source": self.name}

    def valuation_history(self, code: str) -> dict:
        # 乐咕乐股：10 年 pe/pb/ps/股息率（正是 M7 估值分位所需）
        df = self._ak.stock_a_indicator_lg(symbol=code)
        records = [
            {
                "trade_date": str(r["trade_date"]).replace("-", ""),
                "pe": to_float(r.get("pe")),
                "pe_ttm": to_float(r.get("pe_ttm")),
                "pb": to_float(r.get("pb")),
                "ps": to_float(r.get("ps")),
                "dv_ttm": to_float(r.get("dv_ttm")),
                "total_mv": to_float(r.get("total_mv")),
            }
            for _, r in df.iterrows()
        ]
        return {"records": records, "source": self.name}

    def dividends(self, code: str) -> dict:
        # 巨潮分红：报告期, 每股派息(税前)[元], 进度
        df = self._ak.stock_dividend_cninfo(symbol=code)
        records = [
            {
                "period": str(r.get("报告期", "") or "").replace("-", ""),
                "cash_div_tax": to_float(r.get("每股派息(税前)[元]")),
                "div_proc": str(r.get("进度", "") or ""),
            }
            for _, r in df.iterrows()
            if str(r.get("报告期", "") or "").replace("-", "")
        ]
        return {"records": records, "source": self.name}
