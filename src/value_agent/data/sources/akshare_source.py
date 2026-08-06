"""AkShare 数据源（新浪/东财/乐咕乐股，全免费、无 token）。

- 覆盖最全：公司信息（含行业）、财务指标、前复权日线、
  估值历史（乐咕乐股 pe/pb/ps/股息率，10 年）、分红（东财）
- 风险：抓取东财/新浪公开接口，**海外 IP（Render）可能被限流/超时**，
  用 `python -m value_agent data ping` 实测；本地开发 100% 可用
"""
from __future__ import annotations

import datetime
import logging

from .base import DataSource, to_float
from .urls import source_url

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

    def _retry(self, name: str, fn, tries: int = 2):
        """对瞬时网络错误做有限重试（东财/新浪接口偶发 RemoteDisconnected）。"""
        last: Exception | None = None
        for i in range(tries):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last = exc
                if i < tries - 1:
                    import time

                    time.sleep(0.6 * (i + 1))
        logger.warning("[akshare] %s 重试 %d 次仍失败：%s", name, tries, last)
        raise last

    def company_info(self, code: str) -> dict:
        return self._retry("company_info", lambda: self._company_info(code))

    def _company_info(self, code: str) -> dict:
        """公司信息：东财个股信息优先；接口失败（如 JSONDecodeError）回退巨潮公司概况。"""
        try:
            df = self._ak.stock_individual_info_em(symbol=code)
            kv = dict(zip(df["item"], df["value"]))
            return {
                "code": code,
                "ts_code": code,
                "name": str(kv.get("股票简称", code)),
                "industry": str(kv.get("行业", "")),
                "list_date": str(kv.get("上市时间", "") or ""),
                "source": self.name,
                "url": source_url("company", code),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[akshare] 东财个股信息 %s 失败（%s），回退巨潮公司概况",
                code, type(exc).__name__,
            )
            return self._company_info_cninfo(code)

    def _company_info_cninfo(self, code: str) -> dict:
        """巨潮公司概况兜底：名称 / 所属行业 / 上市日期。"""
        df = self._ak.stock_profile_cninfo(symbol=code)
        if df is None or df.empty:
            return {
                "code": code, "ts_code": code, "name": code,
                "industry": "", "list_date": "",
                "source": self.name, "url": source_url("company", code),
            }
        row = df.iloc[0]
        return {
            "code": code,
            "ts_code": code,
            "name": str(row.get("A股简称") or row.get("公司名称") or code),
            "industry": str(row.get("所属行业") or ""),
            "list_date": str(row.get("上市日期") or ""),
            "source": self.name,
            "url": source_url("company", code),
        }

    def financials(self, code: str, years: int = 10) -> dict:
        return self._retry("financials", lambda: self._financials(code, years))

    def _financials(self, code: str, years: int = 10) -> dict:
        df = self._ak.stock_financial_analysis_indicator(symbol=code)
        # 接口按日期升序返回 → 取最新 years*4 期（避免取到最旧数据）
        df = df.tail(years * 4)
        # 列名（新浪）：日期, 净资产收益率(%), 毛利率(%), 净利率(%), 资产负债率(%), 每股收益, 每股经营现金流
        records: list[dict] = []
        for _, r in df.iterrows():
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
                    "ocfps": to_float(r.get("每股经营性现金流(元)") or r.get("每股经营现金流")),
                    "eps": to_float(r.get("摊薄每股收益(元)") or r.get("加权每股收益(元)") or r.get("每股收益")),
                    "ocf_to_np": None,
                }
            )
        return {"records": records, "source": self.name, "url": source_url("financials", code)}

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        return self._retry("daily_prices", lambda: self._daily_prices(code, start, end))

    def _daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        # 接口需显式日期范围（None 会返回空）
        if start is None:
            start = (datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=365 * 10)).strftime("%Y%m%d")
        if end is None:
            end = datetime.datetime.now(datetime.UTC).date().strftime("%Y%m%d")
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
        return {"records": records, "source": self.name, "url": source_url("daily_price", code)}

    def valuation_history(self, code: str) -> dict:
        return self._retry("valuation_history", lambda: self._valuation_history(code))

    def _valuation_history(self, code: str) -> dict:
        # 百度股市通估值历史：按指标分别拉取后按日期合并（akshare>=1.18 已移除乐咕接口）。
        # 注意：stock_zh_valuation_baidu 不支持「市销率」（可选值见 akshare docstring），
        # 传入会返回空结构报 NoneType 错；PS 无下游消费，records.ps 保持 None。
        indicators = {
            "pe_ttm": "市盈率(TTM)",
            "pb": "市净率",
        }
        merged: dict[str, dict] = {}
        for key, ind in indicators.items():
            try:
                df = self._ak.stock_zh_valuation_baidu(
                    symbol=code, indicator=ind, period="近十年"
                )
                for _, r in df.iterrows():
                    d = str(r.get("date") or "").replace("-", "")
                    if not d or d in ("nan", "NaT"):
                        continue
                    merged.setdefault(d, {})[key] = to_float(r.get("value"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("估值指标 %s 获取失败：%s", ind, exc)
        records = [
            {
                "trade_date": d,
                "pe": v.get("pe_ttm"),
                "pe_ttm": v.get("pe_ttm"),
                "pb": v.get("pb"),
                "ps": v.get("ps"),
                "dv_ttm": None,
                "total_mv": None,
            }
            for d, v in sorted(merged.items())
        ]
        return {"records": records, "source": self.name, "url": source_url("valuation_history", code)}

    def dividends(self, code: str) -> dict:
        return self._retry("dividends", lambda: self._dividends(code))

    def _dividends(self, code: str) -> dict:
        # 东财分红明细：报告期(YYYY-MM-DD) / 现金分红-现金分红比例(每10股派X元) / 方案进度
        # （旧巨潮接口 stock_dividend_cninfo 列名已变更：报告期→报告时间、每股派息→派息比例，不再可用）
        df = self._ak.stock_fhps_detail_em(symbol=code)
        records = _dividend_records_from_df(df)
        return {"records": records, "source": self.name, "url": source_url("dividends", code)}


def _dividend_records_from_df(df) -> list[dict]:
    """把东财 stock_fhps_detail_em 的 DataFrame 转成统一分红记录（纯函数，可离线测试）。

    - 只保留「已实施」分红（排除预披露/预案，避免用未来/未兑现派息估值）；
    - 现金分红-现金分红比例 是「每 10 股派 X 元」→ 换算每股派息；
    - 输出按 period 倒序（最新在前，M4 ddm 取第一条）。
    """
    records: list[dict] = []
    for _, r in df.iterrows():
        period = str(r.get("报告期", "") or "").replace("-", "")
        proc = str(r.get("方案进度", "") or "")
        per_10 = to_float(r.get("现金分红-现金分红比例"))
        # not (per_10 > 0) 同时滤掉 NaN / None / 0
        if not period or "实施" not in proc or per_10 is None or not (per_10 > 0):
            continue
        records.append({
            "period": period,  # YYYYMMDD（校验要求）
            "cash_div_tax": round(per_10 / 10.0, 4),  # 每10股派X元 → 每股派息
            "div_proc": proc,
        })
    records.sort(key=lambda r: r["period"], reverse=True)
    return records
