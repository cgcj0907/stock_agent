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
        # 列名（新浪 displaytype=4，已验证 600519/000333/601919/600036 列稳定）：
        # 日期, 净资产收益率(%), 毛利率(%), 净利率(%), 资产负债率(%),
        # 摊薄每股收益(元), 每股经营性现金流(元), 经营现金净流量与净利润的比率(%) ← ocf_to_np
        # 注意：列名带 (%)，但 akshare 返回的**原始值已经是比率**（2024 茅台 = 1.0350，
        # 与 ocfps/eps=73.61/71.12 完全一致），**不要**再除以 100。
        # 季度口径波动大，M2/M4 均只用年报（period 以 1231 结尾）。
        has_ratio_col = "经营现金净流量与净利润的比率(%)" in df.columns
        records: list[dict] = []
        for _, r in df.iterrows():
            period = str(r.get("日期", "") or "")
            if not period or period in ("nan", "-"):
                continue
            eps = to_float(r.get("摊薄每股收益(元)") or r.get("加权每股收益(元)") or r.get("每股收益"))
            ocfps = to_float(r.get("每股经营性现金流(元)") or r.get("每股经营现金流"))
            ocf_to_np = to_float(r.get("经营现金净流量与净利润的比率(%)")) if has_ratio_col else None
            # 兜底：新浪个别页面缺比率列时，用每股口径估算（每股经营现金流/每股收益 = 总额口径，等价）
            if ocf_to_np is None and ocfps is not None and eps and eps > 0:
                ocf_to_np = round(ocfps / eps, 4)
            records.append(
                {
                    "period": period.replace("-", ""),
                    "roe": to_float(r.get("净资产收益率(%)")),
                    "grossprofit_margin": to_float(r.get("毛利率(%)")),
                    "netprofit_margin": to_float(r.get("净利率(%)")),
                    "debt_to_assets": to_float(r.get("资产负债率(%)"), 100.0),  # % → 小数
                    "ocfps": ocfps,
                    "eps": eps,
                    "ocf_to_np": ocf_to_np,
                }
            )
        return {"records": records, "source": self.name, "url": source_url("financials", code)}

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        return self._retry("daily_prices", lambda: self._daily_prices(code, start, end))

    def _eastmoney_kline(self, code: str, start: str, end: str):
        """用 curl_cffi（Chrome TLS 指纹伪装）+ 浏览器请求头直连东财 kline 接口。

        akshare 的 stock_zh_a_hist 用裸 requests（标准 Python TLS 指纹、无 Referer），
        容易被东财反爬识别并断连（ConnectionError/RemoteDisconnected，尤其云机房 IP）。
        这里伪装成真实 Chrome 浏览器请求，显著降低被风控概率。
        """
        from curl_cffi import requests as cfrequests  # akshare 依赖，已在镜像内

        market = 1 if code.startswith("6") else 0
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": "101",  # daily
            "fqt": "1",    # 前复权
            "secid": f"{market}.{code}",
            "beg": start,
            "end": end,
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        resp = cfrequests.get(url, params=params, headers=headers, impersonate="chrome", timeout=15)
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        klines = data.get("klines") or []
        rows = [k.split(",") for k in klines]
        import pandas as pd

        return pd.DataFrame(
            rows,
            columns=["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额",
                     "振幅", "涨跌幅", "涨跌额", "换手率"],
        )

    def _daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        # 接口需显式日期范围（None 会返回空）
        if start is None:
            start = (datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=365 * 10)).strftime("%Y%m%d")
        if end is None:
            end = datetime.datetime.now(datetime.UTC).date().strftime("%Y%m%d")
        try:
            df = self._eastmoney_kline(code, start, end)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[daily] %s curl_cffi 东财失败，回退 akshare：%s", code, exc)
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
