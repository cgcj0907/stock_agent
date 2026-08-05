"""LLM 输出解析与提示词规范测试。"""
from __future__ import annotations

from value_agent.core.llm import LLM_JSON_RULE, parse_llm_json


def test_parse_plain_json():
    text = '{"key_assumptions": ["a", "b"], "verdict": "x"}'
    assert parse_llm_json(text) == {"key_assumptions": ["a", "b"], "verdict": "x"}


def test_parse_fenced_json():
    text = '```json\n{"width": "宽", "evidence": ["e1"]}\n```'
    assert parse_llm_json(text) == {"width": "宽", "evidence": ["e1"]}


def test_parse_json_with_surrounding_text():
    text = '好的，结果如下：{"risks": ["r1"]} 以上。'
    assert parse_llm_json(text) == {"risks": ["r1"]}


def test_parse_invalid_returns_none():
    assert parse_llm_json("") is None
    assert parse_llm_json("这不是 JSON") is None
    assert parse_llm_json('{"a": }') is None
    assert parse_llm_json("[1, 2, 3]") is None  # 非对象不返回


def test_parse_returns_none_for_array():
    assert parse_llm_json('[{"a": 1}]') is None


def test_llm_json_rule_is_strict():
    assert "JSON" in LLM_JSON_RULE
    assert "不要 Markdown" in LLM_JSON_RULE
    assert "不要代码块" in LLM_JSON_RULE
