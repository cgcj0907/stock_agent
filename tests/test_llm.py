"""LLM 输出解析与提示词规范测试。"""
from __future__ import annotations

from value_agent.core.config import _load_dotenv
from value_agent.core.llm import LLM_JSON_RULE, _prefixed_model, parse_llm_json


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


def test_prefixed_model_adds_provider_prefix():
    assert _prefixed_model("deepseek-chat", "deepseek") == "deepseek/deepseek-chat"
    assert _prefixed_model("gpt-4o-mini", "openai") == "openai/gpt-4o-mini"
    assert _prefixed_model("deepseek/deepseek-chat", "deepseek") == "deepseek/deepseek-chat"  # 已带前缀不重复
    assert _prefixed_model("", "deepseek") == "deepseek-chat"  # 空模型回落默认


def test_load_dotenv_strips_inline_comment_and_quotes(tmp_path):
    """.env 行内注释与引号处理（LLM_PROVIDER=deepseek   # deepseek / openai 场景）。"""
    env = tmp_path / ".env"
    env.write_text('LLM_PROVIDER=deepseek   # deepseek / openai / qwen / ollama\nKEY="double-quoted"\n', encoding="utf-8")
    import os

    os.environ.pop("LLM_PROVIDER", None)
    os.environ.pop("KEY", None)
    _load_dotenv(str(env))
    assert os.environ["LLM_PROVIDER"] == "deepseek"
    assert os.environ["KEY"] == "double-quoted"


def test_llm_json_rule_is_strict():
    assert "JSON" in LLM_JSON_RULE
    assert "不要 Markdown" in LLM_JSON_RULE
    assert "不要代码块" in LLM_JSON_RULE

# ---------- 流式增量解析 ----------
def test_stream_delta_extracts_dict_content():
    from value_agent.core.llm import _stream_delta

    chunk = {"choices": [{"delta": {"content": "商业"}}]}
    assert _stream_delta(chunk) == "商业"


def test_stream_delta_extracts_object_content():
    from value_agent.core.llm import _stream_delta

    class _Delta:
        content = "模式"

    class _Choice:
        delta = _Delta()

    class _Chunk:
        def __init__(self) -> None:
            self.choices = [_Choice()]

    assert _stream_delta(_Chunk()) == "模式"


def test_stream_delta_ignores_empty_or_meta_chunks():
    from value_agent.core.llm import _stream_delta

    assert _stream_delta({"choices": [{"delta": {}}]}) is None
    assert _stream_delta({"choices": [{"delta": {"content": ""}}]}) is None
    assert _stream_delta({"choices": [{"delta": {"role": "assistant"}}]}) is None
    assert _stream_delta({}) is None
    assert _stream_delta(None) is None


def test_stream_parts_extracts_content_and_thinking():
    """同一块同时含正文与思考（DeepSeek Reasoner）时两类都产出。"""
    from value_agent.core.llm import _stream_parts

    chunk = {
        "choices": [
            {
                "delta": {
                    "reasoning_content": "先判断生意类型",
                    "content": "{\"business_type\": \"cyclical\"}",
                }
            }
        ]
    }
    assert list(_stream_parts(chunk)) == [
        ("content", '{"business_type": "cyclical"}'),
        ("thinking", "先判断生意类型"),
    ]


def test_stream_parts_falls_back_to_reasoning_field():
    """OpenAI o 系用 reasoning 字段：也应识别为 thinking。"""
    from value_agent.core.llm import _stream_parts

    class _Delta:
        reasoning = "深入思考中"
        content = None

    class _Choice:
        delta = _Delta()

    class _Chunk:
        def __init__(self) -> None:
            self.choices = [_Choice()]

    assert list(_stream_parts(_Chunk())) == [("thinking", "深入思考中")]


def test_stream_chat_yields_deltas_in_order(monkeypatch):
    """stream_chat 应逐个 yield (kind, delta)；空/元数据块被跳过。"""
    import sys

    from value_agent.core.llm import LlmClient

    captured = {}

    class _FakeLiteLLM:
        @staticmethod
        def completion(**kwargs):
            captured["stream"] = kwargs.get("stream")
            captured["messages"] = kwargs["messages"]

            def _gen():
                yield {"choices": [{"delta": {"content": "你"}}]}
                yield {"choices": [{"delta": {"reasoning_content": "思考"}}]}
                yield {"choices": [{"delta": {"content": "好"}}]}
                yield {"choices": [{"delta": {}}]}
                yield {"choices": [{"delta": {"content": "！"}}]}

            return _gen()

    monkeypatch.setitem(sys.modules, "litellm", _FakeLiteLLM)

    client = LlmClient(api_key="k", base_url="https://x/v1")
    out = list(client.stream_chat("sys", "usr"))
    assert out == [
        ("content", "你"),
        ("thinking", "思考"),
        ("content", "好"),
        ("content", "！"),
    ]
    assert captured["stream"] is True
    assert [m["role"] for m in captured["messages"]] == ["system", "user"]
