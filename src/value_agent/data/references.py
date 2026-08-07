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
_FETCH_MAX = 24


def _with_retry(fn, attempts: int = 2, delay: float = 0.6):
    """东财等接口偶发 SSL/网络断连，轻量重试。"""
    import time

    last: Exception | None = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(delay)
    raise last  # type: ignore[misc]


def _refs_from_df(
    df: Any,
    title_cols: tuple[str, ...],
    url_cols: tuple[str, ...],
    snippet_cols: tuple[str, ...] = (),
    meta_cols: tuple[str, ...] = (),
    limit: int | None = None,
    snippet_len: int = 150,
) -> list[dict]:
    """按可能的列名取「标题/链接」，可选带正文摘要/元信息，去重后返回 [{title, url, snippet?, meta?}]。

    - snippet：正文摘要（如新闻内容），截断到 snippet_len；
    - meta：来源/机构/日期等短元信息，拼接进 snippet 括号里，供 LLM 参考。
    """
    if df is None or getattr(df, "empty", True):
        return []
    title_col = next((c for c in title_cols if c in df.columns), None)
    url_col = next((c for c in url_cols if c in df.columns), None)
    if title_col is None or url_col is None:
        logger.warning("[refs] DataFrame 缺少标题/链接列（%s / %s）", title_cols, url_cols)
        return []
    snippet_col = next((c for c in snippet_cols if c in df.columns), None)
    refs: list[dict] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        url = str(row.get(url_col) or "").strip()
        if not url or url in seen:
            continue
        title = str(row.get(title_col) or url).strip()
        ref: dict = {"title": title, "url": url}
        if snippet_col:
            s = str(row.get(snippet_col) or "").strip()
            if s:
                if len(s) > snippet_len:
                    s = s[:snippet_len].rstrip() + "…"
                ref["snippet"] = s
        meta_parts = [str(row.get(c)).strip() for c in meta_cols if str(row.get(c) or "").strip()]
        if meta_parts:
            ref["meta"] = " · ".join(meta_parts)
        seen.add(url)
        refs.append(ref)
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

    def reports(self, code: str, years: int = 3, category: str = "年报") -> list[dict]:
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

    def notices(self, code: str, days: int = 180, limit: int = 8) -> list[dict]:
        """东方财富个股公告（财务报告类）链接。"""
        ak = self._akshare()
        today = datetime.datetime.now(datetime.UTC).date()
        begin = today - datetime.timedelta(days=days)
        try:
            df = _with_retry(
                lambda: ak.stock_individual_notice_report(
                    security=code, symbol="财务报告",
                    begin_date=begin.strftime("%Y%m%d"),
                    end_date=today.strftime("%Y%m%d"),
                )
            )
            return _refs_from_df(df, ("公告标题",), ("网址", "公告链接"), limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[refs] %s 公告获取失败：%s", code, exc)
            return []

    def news(self, code: str, limit: int = 6) -> list[dict]:
        """东方财富个股新闻链接。"""
        ak = self._akshare()
        try:
            df = _with_retry(lambda: ak.stock_news_em(symbol=code))
            return _refs_from_df(
                df,
                ("新闻标题",),
                ("新闻链接",),
                snippet_cols=("新闻内容",),
                meta_cols=("文章来源", "发布时间"),
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[refs] %s 新闻获取失败：%s", code, exc)
            return []

    def research(self, code: str, limit: int = 4) -> list[dict]:
        """东方财富个股研报 PDF 链接。"""
        ak = self._akshare()
        try:
            df = _with_retry(lambda: ak.stock_research_report_em(symbol=code))
            # 不同版本列名：报告名称 / 研究报告名称
            return _refs_from_df(
                df,
                ("报告名称", "研究报告名称"),
                ("报告PDF链接",),
                meta_cols=("机构", "东财评级", "日期"),
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[refs] %s 研报获取失败：%s", code, exc)
            return []

    def fetch(self, code: str, limit: int = 5, slot: int = 0) -> list[dict]:
        """汇总真实参考资料：年报 + 公告 + 新闻 + 研报，按 url 去重。

        为避免「全是财报/分红公告、且多个模块拿到同一份」：
        - 财报类（年报+财务报告公告）与资讯类（新闻+研报）**交错合并**，
          保证任意一段都同时含财报与资讯链接；
        - 进程内缓存完整池（最多 _FETCH_MAX 条），调用方用 slot 取不同片段
          （不同模块传不同 slot，避免链接雷同）。
        """
        if code not in _CACHE:
            seen: set[str] = set()

            def _dedupe(refs: list[dict]) -> list[dict]:
                out: list[dict] = []
                for r in refs:
                    if r["url"] not in seen:
                        seen.add(r["url"])
                        out.append(r)
                return out

            fin = _dedupe(self.reports(code) + self.notices(code))
            info = _dedupe(self.news(code) + self.research(code))
            pool: list[dict] = []
            i = j = 0
            while (i < len(fin) or j < len(info)) and len(pool) < _FETCH_MAX:
                if i < len(fin):
                    pool.append(fin[i])
                    i += 1
                if j < len(info):
                    pool.append(info[j])
                    j += 1
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.clear()
            _CACHE[code] = pool
        pool = _CACHE[code]
        if not pool:
            return []
        n = len(pool)
        start = (slot * limit) % n
        return pool[start : start + limit]


def format_reference_list(refs: list[dict]) -> str:
    """把参考清单格式化为提示词段落（编号 + 标题 + 摘要/元信息），供 LLM 筛选引用。"""
    if not refs:
        return ""
    lines: list[str] = []
    for i, r in enumerate(refs, 1):
        parts = [str(r.get("title") or "")]
        snip = str(r.get("snippet") or "").strip()
        meta = str(r.get("meta") or "").strip()
        if snip:
            parts.append(snip)
        if meta:
            parts.append(f"[{meta}]")
        lines.append(f"{i}. {' '.join(parts)}")
    return "参考资料清单（只可引用以下真实来源，不得编造标题或链接）：\n" + "\n".join(lines)


def select_references(refs: list[dict], indices) -> list[dict]:
    """按 LLM 输出的 1-based 下标过滤真实链接；无/非法输入回退全部。"""
    if not refs or indices is None:
        return list(refs)
    if isinstance(indices, int):
        indices = [indices]
    out: list[dict] = []
    if isinstance(indices, list):
        for idx in indices:
            try:
                i = int(idx) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(refs) and refs[i] not in out:
                out.append(refs[i])
    return out or list(refs)
