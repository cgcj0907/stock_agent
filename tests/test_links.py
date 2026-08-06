"""参考文章链接校验测试（httpx MockTransport，不依赖外网）。"""
from __future__ import annotations

import httpx

from value_agent.core.links import validate_reference_links


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_valid_html_links_kept():
    t = _transport(lambda req: httpx.Response(200, headers={"content-type": "text/html"}, request=req))
    out = validate_reference_links(
        [{"title": "年报", "url": "https://example.com/a"}, "https://example.com/b"],
        transport=t,
    )
    assert out == [
        {"title": "年报", "url": "https://example.com/a"},
        {"title": "https://example.com/b", "url": "https://example.com/b"},
    ]


def test_404_dropped_200_kept():
    def handler(req):
        if req.url.path == "/ok":
            return httpx.Response(200, headers={"content-type": "text/html"}, request=req)
        return httpx.Response(404, request=req)

    out = validate_reference_links(
        [
            {"title": "坏的", "url": "https://example.com/missing"},
            {"title": "好的", "url": "https://example.com/ok"},
        ],
        transport=_transport(handler),
    )
    assert out == [{"title": "好的", "url": "https://example.com/ok"}]


def test_head_405_falls_back_to_get():
    def handler(req):
        if req.method == "HEAD":
            return httpx.Response(405, request=req)
        return httpx.Response(200, headers={"content-type": "text/html"}, request=req)

    out = validate_reference_links(["https://example.com/a"], transport=_transport(handler))
    assert len(out) == 1


def test_pdf_content_type_kept():
    t = _transport(lambda req: httpx.Response(200, headers={"content-type": "application/pdf"}, request=req))
    out = validate_reference_links(["https://example.com/report.pdf"], transport=t)
    assert len(out) == 1


def test_network_error_dropped():
    def handler(req):
        raise httpx.ConnectError("connection refused", request=req)

    out = validate_reference_links(["https://example.com/a"], transport=_transport(handler))
    assert out == []


def test_all_invalid_returns_empty():
    def handler(req):
        return httpx.Response(404, request=req)

    assert validate_reference_links(["https://example.com/a", "https://example.com/b"], transport=_transport(handler)) == []


def test_non_http_scheme_dropped():
    out = validate_reference_links(
        ["javascript:alert(1)", "ftp://example.com/x", {"title": "x", "url": "not-a-url"}],
        transport=_transport(lambda req: httpx.Response(200, request=req)),
    )
    assert out == []


def test_empty_or_none_returns_empty():
    assert validate_reference_links(None) == []
    assert validate_reference_links([]) == []
    assert validate_reference_links("") == []
