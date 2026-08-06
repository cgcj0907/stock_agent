"""公司参考资料工具：通过 AkShare 获取真实有效的财报/公告/新闻/研报链接。

LLM 会编造"看似合理"的 URL（如臆造的交易所公告地址），本工具改用专业数据源：
- 巨潮资讯（cninfo）：年报披露详情页
- 东方财富：个股公告 / 个股新闻 / 个股研报 PDF
所有链接均来自真实数据源，agent 把它注入 references，保证链接有效可访问。
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 进程内缓存：同一次分析里 11 个模块查同一只股票，只拉一次
_CACHE: dict[str, list[dict]] = {}
_CACHE_MAX = 256
_FETCH_MAX = 10


def _refs_from_df(
    df: Any,
    title_cols: tuple[str, ...],
    url_cols: tuple[str, ...],
    limit: int | None = None,
) -> list[dict]:
    """按可能的列名取「标题/链接」，去重后返回 [{title, url}]。"""
    if df is None or getattr(df, "empty", True):
        return []
    title_col = next((c for c in title_cols if c in df.columns), None)
    url_col = next((c for c in url_cols if c in df.columns), None)
    if title_col is None or url_col is None:
        logger.warning("[refs] DataFrame 缺少标题/链接列（%s / %s）", title_cols, url_cols)
        return []
    refs: list[dict] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        url = str(row.get(url_col) or "").strip()
        if not url or url in seen:
            continue
        title = str(row.get(title_col) or url).strip()
        seen.add(url)
        refs.append({"title": title, "url": url})
        if limit is not None and len(refs) >= limit:
            break
    return refs


class CompanyReferences:
    """按股票代码获取真实参考资料链接（财报/公告/新闻/研报）。"""

    def __init__(self) -> None:
        self._ak = None

    def _akshare(self):
        if self._ak is None:
            try:
                import akshare as ak
            except ImportError as exc:
                raise ImportError("未安装 akshare：`pip install akshare`（本地免费方案）") from exc
            self._ak = ak
        return self._ak

    def reports(self, code: str, years: int = 2, category: str = "年报") -> list[dict]:
        """巨潮资讯披露链接（cninfo 详情页，长期有效）。"""
        ak = self._akshare()
        today = datetime.datetime.now(datetime.UTC).date()
        start = today - datetime.timedelta(days=365 * years + 30)
        try:
            df = ak.stock_zh_a_disclosure_report_cninfo(
                symbol=code, market="沪深京", category=category,
                start_date=start.strftime("%Y%m%d"),
                end_date=today.strftime("%Y%m%d"),
            )
            return _refs_from_df(df, ("公告标题",), ("公告链接", "网址", "链接"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[refs] %s %s 获取失败：%s", code, category, exc)
            return []

    def notices(self, code: str, days: int = 180) -> list[dict]:
        """东方财富个股公告（财务报告类）链接。"""
        ak = self._akshare()
        today = datetime.datetime.now(datetime.UTC).date()
        begin = today - datetime.timedelta(days=days)
        try:
            df = ak.stock_individual_notice_report(
                security=code, symbol="财务报告",
                begin_date=begin.strftime("%Y%m%d"),
                end_date=today.strftime("%Y%m%d"),
            )
            return _refs_from_df(df, ("公告标题",), ("网址", "公告链接"), limit=6)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[refs] %s 公告获取失败：%s", code, exc)
            return []

    def news(self, code: str, limit: int = 5) -> list[dict]:
        """东方财富个股新闻链接。"""
        ak = self._akshare()
        try:
            df = ak.stock_news_em(symbol=code)
            return _refs_from_df(df, ("新闻标题",), ("新闻链接",), limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[refs] %s 新闻获取失败：%s", code, exc)
            return []

    def research(self, code: str, limit: int = 3) -> list[dict]:
        """东方财富个股研报 PDF 链接。"""
        ak = self._akshare()
        try:
            df = ak.stock_research_report_em(symbol=code)
            return _refs_from_df(df, ("研究报告名称",), ("报告PDF链接",), limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[refs] %s 研报获取失败：%s", code, exc)
            return []

    def fetch(self, code: str, limit: int = 5) -> list[dict]:
        """汇总真实参考资料：年报 + 公告 + 新闻 + 研报，按 url 去重。

        进程内缓存完整列表（最多 _FETCH_MAX 条），调用方按 limit 取前 N 条。
        """
        if code not in _CACHE:
            refs: list[dict] = []
            seen: set[str] = set()
            for group in (
                self.reports(code),
                self.notices(code),
                self.news(code),
                self.research(code),
            ):
                for r in group:
                    if r["url"] not in seen:
                        seen.add(r["url"])
                        refs.append(r)
                    if len(refs) >= _FETCH_MAX:
                        break
                if len(refs) >= _FETCH_MAX:
                    break
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.clear()
            _CACHE[code] = refs
        return _CACHE[code][:limit]
