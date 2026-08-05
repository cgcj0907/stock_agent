"""数据来源文章/页面 URL 生成。

AkShare 各接口底层来自不同公开页面，这里把「数据集 → 文章级 URL」统一映射，
供数据源返回、DataManager 透传、以及各智能体写 evidence 引用（可点击溯源）。
"""
from __future__ import annotations

import datetime


def market_prefix(code: str) -> str:
    """沪深前缀：6/9 开头按沪市（sh），其余按深市（sz）。"""
    return "sh" if str(code).startswith(("6", "9")) else "sz"


def eastmoney_f10_url(code: str, page: str = "NewFinanceAnalysis") -> str:
    """东方财富 F10 页（公司概况/财务分析等），code 参数为大写市场+代码。"""
    sym = f"{market_prefix(code).upper()}{code}"
    return f"https://emweb.securities.eastmoney.com/PC_HSF10/{page}/Index?type=web&code={sym}"


def eastmoney_quote_url(code: str) -> str:
    """东方财富个股行情页（含 K 线/估值）。"""
    return f"https://quote.eastmoney.com/{market_prefix(code)}{code}.html"


def sina_financial_indicators_url(code: str) -> str:
    """新浪财经财务指标页（对应 stock_financial_analysis_indicator）。"""
    year = datetime.date.today().year
    return (
        "https://money.finance.sina.com.cn/corp/go.php/"
        f"vFD_FinancialGuideLine/stockid/{code}/ctrl/{year}/displaytype/4.phtml"
    )


def baidu_valuation_url(code: str) -> str:
    """百度股市通估值页（对应 stock_zh_valuation_baidu，pe/pb/ps 近十年）。"""
    return f"https://gushitong.baidu.com/stock/ab-{code}"


def cninfo_disclosure_url(code: str) -> str:
    """巨潮资讯个股披露页（对应 stock_dividend_cninfo 分红/公告）。"""
    return f"https://www.cninfo.com.cn/new/disclosure/stock?stockCode={code}"


_SOURCE_URL_FN = {
    "company": lambda code: eastmoney_f10_url(code, "CompanySurvey"),
    "financials": sina_financial_indicators_url,
    "daily_price": eastmoney_quote_url,
    "valuation_history": baidu_valuation_url,
    "dividends": lambda code: eastmoney_f10_url(code, "BonusFinancing"),  # 东财 F10 分红融资页
}


def source_url(dataset: str, code: str) -> str:
    """按数据集名返回文章级数据来源 URL；未知数据集返回空串。"""
    fn = _SOURCE_URL_FN.get(dataset)
    return fn(code) if fn else ""
