"""参考文章链接校验：只保留真实可访问的链接，过滤 404 / 超时 / 非网页。

LLM 可能编造"看似合理"的链接，展示前统一做 HTTP 校验：
- 归一化 references（字符串 / {title,url} / {url} 均可）
- HEAD 优先，站点禁止 HEAD（405/501）时回退 GET
- 2xx 且内容类型为网页 / PDF（财报公告常为 PDF）才算有效
- 校验失败（404/超时/网络错误）一律丢弃，全部无效返回 []
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 4.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; value-agent/0.1; "
        "+https://github.com/link-check)"
    )
}


def _as_refs(value: Any) -> list[dict]:
    """把 LLM 返回的 references 归一化为 [{title, url}]；非法项丢弃。"""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    refs: list[dict] = []
    for item in items:
        if isinstance(item, str):
            url = item.strip()
            if url:
                refs.append({"title": url, "url": url})
        elif isinstance(item, dict):
            url = str(item.get("url") or item.get("link") or item.get("href") or "").strip()
            title = str(item.get("title") or item.get("name") or url).strip()
            if url:
                refs.append({"title": title, "url": url})
    return refs


def _url_ok(url: str, timeout: float, transport=None) -> bool:
    """单个链接是否真实可访问。任何异常按无效处理，绝不抛出。"""
    import httpx

    if not url.startswith(("http://", "https://")):
        return False
    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers=_HEADERS, transport=transport
        ) as client:
            resp = client.head(url)
            if resp.status_code in (405, 501):  # 站点禁止 HEAD → 回退 GET
                resp = client.get(url)
            if resp.status_code < 200 or resp.status_code >= 300:
                logger.info("[links] 无效状态 %s -> %s", resp.status_code, url)
                return False
            ctype = (resp.headers.get("content-type") or "").lower()
            if ctype and not (
                ctype.startswith("text/") or "html" in ctype or "pdf" in ctype
            ):
                logger.info("[links] 非网页/PDF 内容 %s -> %s", ctype, url)
                return False
            return True
    except Exception as exc:  # noqa: BLE001
        logger.info("[links] 校验失败 %s：%s", url, type(exc).__name__)
        return False


def validate_reference_links(
    value: Any,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    transport=None,
) -> list[dict]:
    """校验并返回真实可访问的参考链接；全部无效时返回 []。

    链接之间并行校验（1-3 条），把最坏延迟压到单链接超时级别。
    """
    refs = _as_refs(value)
    if not refs:
        return []
    with ThreadPoolExecutor(max_workers=min(len(refs), 4)) as pool:
        flags = list(pool.map(lambda r: _url_ok(r["url"], timeout, transport), refs))
    valid = [r for r, ok in zip(refs, flags) if ok]
    if len(valid) != len(refs):
        logger.warning(
            "[links] 过滤 %d/%d 条无效参考链接", len(refs) - len(valid), len(refs)
        )
    return valid
