"""AkShare 数据源（新浪/东财/乐咕乐股，全免费、无 token）。

- 覆盖最全：公司信息（含行业）、财务指标、前复权日线、
  估值历史（乐咕乐股 pe/pb/ps/股息率，10 年）、分红（东财）
- 风险：抓取东财/新浪公开接口，**海外 IP（Render）可能被限流/超时**，
  用 `python -m value_agent data ping` 实测；本地开发 100% 可用
"""
from __future__ import annotations

import datetime
import logging
import re

from .base import DataSource, to_float
from .urls import market_prefix, source_url

logger = logging.getLogger(__name__)


def _first_col(df, *names) -> str | None:
    """返回第一个存在的列名（兼容 AkShare 版本间列名差异，如 毛利率 vs 销售毛利率）。"""
    for n in names:
        if n in df.columns:
            return n
    return None


def _row_value(row, *names):
    """按候选列名取首个非空值（兼容东财三大报表中英文列名）。"""
    for n in names:
        v = row.get(n)
        if v is not None and str(v).strip() not in ("", "nan", "None"):
            return v
    return None


def _first_positive(row, *names):
    """按候选列名取首个正数值（0/负/空视为缺失，避免东财个别字段返回 0.0 的坏值）。"""
    for n in names:
        v = to_float(row.get(n))
        if v is not None and v > 0:
            return v
    return None


def _sina_symbol(code: str) -> str:
    """新浪/腾讯日线接口需要交易所前缀（sh/sz），如 600900 → sh600900。"""
    return ("sh" if str(code).startswith(("6", "9", "5")) else "sz") + str(code).zfill(6)


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
        # 列名兼容：akshare 1.18 起新浪返回「销售毛利率(%)/销售净利率(%)」
        gm_col = _first_col(df, "毛利率(%)", "销售毛利率(%)")
        np_col = _first_col(df, "净利率(%)", "销售净利率(%)")
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
                    "grossprofit_margin": to_float(r.get(gm_col)) if gm_col else None,
                    "netprofit_margin": to_float(r.get(np_col)) if np_col else None,
                    "debt_to_assets": to_float(r.get("资产负债率(%)"), 100.0),  # % → 小数
                    "ocfps": ocfps,
                    "eps": eps,
                    "ocf_to_np": ocf_to_np,
                }
            )
        # 1.1/5.2/5.4/1.4：用东财三大报表（资产负债表/利润表/现金流量表）补充派生字段。
        # best-effort——任一报表失败只缺对应字段，不阻塞基础财务数据。
        try:
            _merge_financial_statements(code, records, self._ak)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[financials] %s 三大报表补充失败（%s），仅用新浪基础指标", code, type(exc).__name__)
        # 新浪个别标的「销售毛利率」为 NaN：用同花顺财务摘要直接补真实毛利率（不自行推算）
        try:
            _backfill_margins_from_ths(code, records, self._ak)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[financials] %s 同花顺毛利率兜底失败（%s）", code, type(exc).__name__)
        return {"records": records, "source": self.name, "url": source_url("financials", code)}

    def daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        return self._retry("daily_prices", lambda: self._daily_prices(code, start, end))

    def _daily_prices(self, code: str, start: str | None = None, end: str | None = None) -> dict:
        # 接口需显式日期范围（None 会返回空）
        if start is None:
            start = (datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=365 * 10)).strftime("%Y%m%d")
        if end is None:
            end = datetime.datetime.now(datetime.UTC).date().strftime("%Y%m%d")

        df, used = self._fetch_daily(code, start, end)
        if used == "eastmoney":
            # 东财：成交量单位=手；换手率=百分数（0.44 → 0.44%）
            records = [
                {
                    "trade_date": str(r["日期"]).replace("-", ""),
                    "open": to_float(r.get("开盘")),
                    "close": to_float(r.get("收盘")),
                    "high": to_float(r.get("最高")),
                    "low": to_float(r.get("最低")),
                    "volume": to_float(r.get("成交量")),
                    "turnover": to_float(r.get("换手率")),
                }
                for _, r in df.iterrows()
            ]
        else:
            # 新浪/腾讯：date 列；成交量单位=股（→手 ÷100）；换手率=小数（0.0044 → 0.44%）
            records = [
                {
                    "trade_date": str(r["date"]).replace("-", ""),
                    "open": to_float(r.get("open")),
                    "close": to_float(r.get("close")),
                    "high": to_float(r.get("high")),
                    "low": to_float(r.get("low")),
                    "volume": to_float(r.get("volume"), 100.0),
                    "turnover": to_float(r.get("turnover"), 0.01),
                }
                for _, r in df.iterrows()
            ]
        return {"records": records, "source": f"{self.name}({used})", "url": source_url("daily_price", code)}

    def _fetch_daily(self, code: str, start: str, end: str):
        """日线多源回退链：东财 akshare → 新浪 → 腾讯（独立主机）。

        东财被反爬断连（RemoteDisconnected，云机房 IP 常见）时，新浪/腾讯是
        独立主机，显著提高「东财封 IP」场景下的可用性。返回 (df, source_key)。
        全部失败抛 ConnectionError（带各源失败摘要，便于上层证据/日志诊断）。
        """
        errors: list[str] = []
        symbol = _sina_symbol(code)
        candidates = [
            ("eastmoney", lambda: self._ak.stock_zh_a_hist(
                symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")),
            ("sina", lambda: self._ak.stock_zh_a_daily(
                symbol=symbol, start_date=start, end_date=end, adjust="qfq")),
            ("tencent", lambda: self._ak.stock_zh_a_hist_tx(
                symbol=symbol, start_date=start, end_date=end, adjust="qfq")),
        ]
        for name, fn in candidates:
            try:
                df = fn()
                if df is not None and not df.empty:
                    return df, name
                errors.append(f"{name}:empty")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}:{type(exc).__name__}")
                logger.warning("[daily] %s 回退 %s 失败：%s", code, name, exc)
        raise ConnectionError("日线全部数据源失败：" + "；".join(errors))

    def valuation_history(self, code: str, start: str | None = None) -> dict:
        return self._retry("valuation_history", lambda: self._valuation_history(code, start))

    def _valuation_history(self, code: str, start: str | None = None) -> dict:
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
            if start is None or d >= start  # 真增量：只保留 start 及之后的估值
        ]
        return {"records": records, "source": self.name, "url": source_url("valuation_history", code)}

    def governance_events(self, code: str) -> dict:
        """治理事件（M6 非分红证据，backlog 6.1）：best-effort 拉取，失败返回空（中性计）。

        当前免费源口径不稳定（东财 F10 质押/减持/回购），逐项 try；任何一项可用即返回，
        全部失败返回空 records——M6 引擎对空事件按中性计，不臆测、不降级。
        """
        records: list[dict] = []
        try:
            # 股权质押（东财：stock_gpzy_pledge_ratio_em 需日期参数，先取最新交易日）
            today = datetime.datetime.now(datetime.UTC).date().strftime("%Y-%m-%d")
            df = self._retry(
                "pledge_ratio",
                lambda: self._ak.stock_gpzy_pledge_ratio_em(symbol=code, date=today),
            )
            if df is not None and not df.empty:
                row = df.iloc[-1]
                ratio = None
                try:
                    ratio = float(str(row.get("质押比例") or "").replace("%", "")) / 100
                except (TypeError, ValueError):
                    pass
                records.append({
                    "kind": "pledges",
                    "event_date": str(row.get("日期") or "").replace("-", ""),
                    "holder": str(row.get("股东名称") or ""),
                    "ratio": ratio,
                    "description": f"股权质押比例 {ratio:.0%}" if ratio is not None else "存在股权质押",
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning("[governance] %s 质押数据获取失败（%s），继续尝试其他事件", code, type(exc).__name__)
        # 6.2：股权集中度（东财十大股东，best-effort）——高度集中给 CONTROL_RISK 风险码
        try:
            df10 = self._retry(
                "top10", lambda: self._ak.stock_gdfx_top_10_em(symbol=code)
            )
            if df10 is not None and not df10.empty:
                ratio_col = next((c for c in ("占总股本比例", "持股比例", "占总股本比例(%)")
                                  if c in df10.columns), None)
                if ratio_col is not None:
                    ratios = []
                    for _, r in df10.iterrows():
                        v = to_float(r.get(ratio_col))
                        if v is not None:
                            ratios.append(v if v <= 1.0 else v / 100.0)
                    if ratios:
                        top10 = round(sum(ratios[:10]), 4)
                        if top10 >= 0.70:
                            records.append({
                                "kind": "control",
                                "event_date": datetime.datetime.now(datetime.UTC).date().strftime("%Y%m%d"),
                                "holder": "",
                                "ratio": top10,
                                "description": f"前十大股东合计持股 {top10:.0%}，股权高度集中",
                            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("[governance] %s 十大股东获取失败（%s），跳过股权集中度", code, type(exc).__name__)
        # 回购/减持等公告类事件免费源口径不稳定，后续接入；当前无则中性计
        return {"records": records, "source": self.name}

    def northbound(self, code: str) -> dict:
        """7.1：北向资金个股持股（东财沪深港通，best-effort，失败返回空）。

        返回 {records: [{trade_date, hold_shares, hold_ratio}]}——当前免费源只给最新快照，
        历史序列口径不稳定；M7 对单点数据按中性处理（有历史才算分位）。
        """
        try:
            df = self._retry(
                "northbound",
                lambda: self._ak.stock_hsgt_hold_stock_em(market="北向", indicator="今日排行"),
            )
            if df is None or df.empty:
                return {"records": [], "source": self.name}
            row = df[df["代码"].astype(str).str.zfill(6) == str(code).zfill(6)]
            if row.empty:
                return {"records": [], "source": self.name}
            r = row.iloc[0]
            today = datetime.datetime.now(datetime.UTC).date().strftime("%Y%m%d")
            ratio = to_float(r.get("今日持股-占流通股比"))
            return {"records": [{
                "trade_date": today,
                "hold_shares": to_float(r.get("今日持股-股数")),
                "hold_ratio": (ratio / 100.0) if ratio is not None else None,
            }], "source": self.name}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[northbound] %s 北向持股获取失败（%s），按空处理", code, type(exc).__name__)
            return {"records": [], "source": self.name}

    def margin(self, code: str) -> dict:
        """7.2：个股两融余额（沪/深交易所按日披露，best-effort，失败返回空）。"""
        try:
            today = datetime.datetime.now(datetime.UTC).date().strftime("%Y%m%d")
            rows: list[dict] = []
            fetchers = [
                ("sse", lambda d: self._ak.stock_margin_detail_sse(date=d)),
                ("szse", lambda d: self._ak.stock_margin_detail_szse(date=d)),
            ]
            for exchange, fn in fetchers:
                try:
                    df = self._retry(f"margin_{exchange}", lambda d=today, f=fn: f(d))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[margin] %s 交易所 %s 两融失败（%s）", code, exchange, type(exc).__name__)
                    continue
                if df is None or df.empty:
                    continue
                code_col = next((c for c in ("标的证券代码", "证券代码") if c in df.columns), None)
                if code_col is None:
                    continue
                row = df[df[code_col].astype(str).str.zfill(6) == str(code).zfill(6)]
                if row.empty:
                    continue
                r = row.iloc[0]
                rows.append({
                    "trade_date": today,
                    "margin_balance": to_float(r.get("融资融券余额") or r.get("融资融券余额(元)")),
                    "fin_balance": to_float(r.get("融资余额") or r.get("融资余额(元)")),
                    "sec_balance": to_float(r.get("融券余额") or r.get("融券余额(元)")),
                })
            return {"records": rows, "source": self.name}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[margin] %s 两融获取失败（%s），按空处理", code, type(exc).__name__)
            return {"records": [], "source": self.name}

    def market_activity(self) -> dict:
        """7.5：大盘情绪——全市场上涨/下跌家数（乐咕乐股，best-effort）。

        返回 {records: [{trade_date, up_count, down_count, breadth}]}，breadth = 上涨/(上涨+下跌)。
        """
        try:
            df = self._retry("market_activity", lambda: self._ak.stock_market_activity_legu())
            if df is None or df.empty:
                return {"records": [], "source": self.name}
            r = df.iloc[-1]
            up = to_float(r.get("上涨"))
            down = to_float(r.get("下跌"))
            breadth = None
            if up is not None and down is not None and (up + down) > 0:
                breadth = round(up / (up + down), 4)
            return {"records": [{
                "trade_date": str(r.get("日期") or datetime.datetime.now(datetime.UTC).date().strftime("%Y%m%d")).replace("-", ""),
                "up_count": up,
                "down_count": down,
                "breadth": breadth,
            }], "source": self.name}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[market_activity] 大盘情绪获取失败（%s），按空处理", type(exc).__name__)
            return {"records": [], "source": self.name}

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


def _col(df, *names):
    """按候选列名取 Series，返回首个存在的列（防东财改列名）。"""
    for n in names:
        if n in df.columns:
            return df[n]
    return None


def _normalize_em_period(v) -> str:
    """东财报告期 → YYYYMMDD（兼容 datetime 字符串「2025-12-31 00:00:00」）。"""
    if v is None:
        return ""
    s = str(v).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    s2 = s.replace("-", "").replace("/", "")
    return s2[:8] if s2.isdigit() and len(s2) >= 8 else ""


def _backfill_margins_from_ths(code: str, records: list[dict], ak) -> None:
    """新浪缺「销售毛利率」时，用同花顺财务摘要直接补真实毛利率/净利率（不自行推算）。

    新浪 `stock_financial_analysis_indicator` 对部分标的（如 600900）销售毛利率返回 NaN，
    而同花顺 `stock_financial_abstract_ths` 直接给出 销售毛利率/销售净利率。
    """
    df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
    if df is None or df.empty:
        return
    by_period: dict[str, dict] = {}
    for _, r in df.iterrows():
        period = str(r.get("报告期") or "").replace("-", "")
        if len(period) == 8 and period.isdigit():
            by_period[period] = {
                "grossprofit_margin": to_float(r.get("销售毛利率")),
                "netprofit_margin": to_float(r.get("销售净利率")),
            }
    filled = 0
    for rec in records:
        m = by_period.get(str(rec.get("period") or ""))
        if not m:
            continue
        if rec.get("grossprofit_margin") is None and m["grossprofit_margin"] is not None:
            rec["grossprofit_margin"] = m["grossprofit_margin"]
            filled += 1
        if rec.get("netprofit_margin") is None and m["netprofit_margin"] is not None:
            rec["netprofit_margin"] = m["netprofit_margin"]
            filled += 1
    if filled:
        logger.debug("[financials] %s 同花顺补齐毛利率/净利率 %d 个值", code, filled)


def _merge_financial_statements(code: str, records: list[dict], ak) -> None:
    """1.1/1.4/5.2/5.4：用东财资产负债表/利润表/现金流量表给 financials 补派生字段。

    - bvps = 归母股东权益 / 股本（NAV 基数）
    - ncav_ps = (流动资产 − 总负债) / 股本（NCAV 基数）
    - rd_ratio = 研发费用 / 营业总收入
    - interest_debt_ratio = (短借+一年内到期+长借+应付债券) / 总资产
    - contract_liability_ratio = 合同负债 / 总资产
    - ocf_to_np_parent = 经营现金流净额 / 归母净利润（1.4 归母口径）
    全部 best-effort：任一报表缺失/字段不匹配，跳过该字段（保持 None）。
    """
    sym = f"{market_prefix(code).upper()}{code}"
    balance, income, cash = {}, {}, {}
    try:
        dfb = ak.stock_balance_sheet_by_report_em(symbol=sym)
        for _, r in dfb.iterrows():
            period = _normalize_em_period(_row_value(r, "报告期", "REPORT_DATE"))
            if not period:
                continue
            balance[period] = {
                "total_assets": to_float(_row_value(r, "资产总计", "资产合计", "TOTAL_ASSETS")),
                "current_assets": to_float(_row_value(r, "流动资产合计", "CURRENT_ASSET_BALANCE", "TOTAL_CURRENT_ASSETS")),
                "total_liabilities": to_float(_row_value(r, "负债合计", "TOTAL_LIABILITIES")),
                # 东财 PARENT_EQUITY_BALANCE 对部分标的（如 000333 美的）返回 0.0，
                # 用 TOTAL_PARENT_EQUITY 兜底并跳过 0/负值（BVPS 坏值事故根因）
                "equity_parent": _first_positive(
                    r, "归属于母公司股东权益合计", "TOTAL_PARENT_EQUITY", "PARENT_EQUITY_BALANCE"
                ),
                "short_loan": to_float(_row_value(r, "短期借款", "SHORT_LOAN")),
                "long_loan": to_float(_row_value(r, "长期借款", "LONG_LOAN")),
                "bond": to_float(_row_value(r, "应付债券", "BOND_PAYABLE")),
                "due_1y": to_float(_row_value(r, "一年内到期的非流动负债", "NONCURRENT_LIAB_1YEAR")),
                "contract_liabilities": to_float(_row_value(r, "合同负债", "CONTRACT_LIAB")),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[financials] %s 资产负债表获取失败（%s）", code, type(exc).__name__)
    try:
        dfi = ak.stock_profit_sheet_by_report_em(symbol=sym)
        for _, r in dfi.iterrows():
            period = _normalize_em_period(_row_value(r, "报告期", "REPORT_DATE"))
            if not period:
                continue
            income[period] = {
                "revenue": to_float(_row_value(r, "营业总收入", "营业收入", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME")),
                "net_profit_parent": to_float(_row_value(r, "归属于母公司所有者的净利润", "净利润", "PARENT_NETPROFIT", "NETPROFIT")),
                "rd_expense": to_float(_row_value(r, "研发费用", "RESEARCH_EXPENSE", "RD_EXPENSE", "DEVELOP_EXPENSE")),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[financials] %s 利润表获取失败（%s）", code, type(exc).__name__)
    try:
        dfc = ak.stock_cash_flow_sheet_by_report_em(symbol=sym)
        for _, r in dfc.iterrows():
            period = _normalize_em_period(_row_value(r, "报告期", "REPORT_DATE"))
            if not period:
                continue
            cash[period] = {
                "ocf_net": to_float(_row_value(
                    r, "经营活动产生的现金流量净额", "经营活动产生的现金流量净额(元)", "NETCASH_OPERATE"
                )),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[financials] %s 现金流量表获取失败（%s）", code, type(exc).__name__)

    for rec in records:
        period = str(rec.get("period") or "")
        if period not in balance and period not in income and period not in cash:
            continue
        b, i, c = balance.get(period, {}), income.get(period, {}), cash.get(period, {})
        eps = rec.get("eps")
        shares = None
        # 股本 = 归母净利润 / 摊薄 EPS（期末股本口径），缺归母利润时用每股字段
        if i.get("net_profit_parent") is not None and eps and eps > 0:
            shares = i["net_profit_parent"] / eps
        if shares and shares > 0:
            eq_parent = b.get("equity_parent")
            if eq_parent is not None and eq_parent > 0:
                rec["bvps"] = round(eq_parent / shares, 4)
            ca, tl = b.get("current_assets"), b.get("total_liabilities")
            if ca is not None and tl is not None and ca > 0 and tl > 0:
                rec["ncav_ps"] = round((ca - tl) / shares, 4)
        # 有息负债率 / 合同负债占比（5.2）
        total_assets = b.get("total_assets")
        if total_assets and total_assets > 0:
            interest = sum(x for x in (b.get("short_loan"), b.get("long_loan"),
                                       b.get("bond"), b.get("due_1y")) if x is not None)
            if interest > 0:
                rec["interest_debt_ratio"] = round(interest / total_assets, 4)
            if b.get("contract_liabilities") is not None:
                rec["contract_liability_ratio"] = round(b["contract_liabilities"] / total_assets, 4)
        # 研发费用率（5.4）
        if i.get("rd_expense") is not None and i.get("revenue") and i["revenue"] > 0:
            rec["rd_ratio"] = round(i["rd_expense"] / i["revenue"], 4)
        # 归母口径 ocf_to_np（1.4）
        if c.get("ocf_net") is not None and i.get("net_profit_parent") not in (None, 0):
            rec["ocf_to_np_parent"] = round(c["ocf_net"] / i["net_profit_parent"], 4)
