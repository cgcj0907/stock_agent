"""LLM 客户端（可选）：统一接入 DeepSeek/Qwen/OpenAI/本地，未配置 key 则返回 None。

设计：分析以规则引擎为主，LLM 只做定性补充；无 LLM 时模块仍可运行（降级为规则结果）。
"""
from __future__ import annotations

import json
import logging
import os
import re

from value_agent.core.config import load_settings

logger = logging.getLogger(__name__)

# 各模块 LLM 定性的统一输出规范：固定 JSON 结构（字段由各模块提示词定义），
# 前端拿到后可直接转成 TS 数据渲染，避免 Markdown/JSON 混排。
LLM_JSON_RULE = (
    "输出规范（务必遵守）：只输出一个合法的 JSON 对象，不要 Markdown、"
    "不要代码块、不要多余文字或解释。"
)


def parse_llm_json(text: str) -> dict | None:
    """从 LLM 回复中解析 JSON 对象；容忍 ```json 代码块与首尾杂文，失败返回 None。"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    # 优先整体解析（严格）：必须是 JSON 对象
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        pass
    # 容忍首尾杂文：提取首个 {...} 块再解析
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(t[start : end + 1])
            return data if isinstance(data, dict) else None
        except (ValueError, TypeError):
            return None
    return None


class LlmClient:
    """轻量 LLM 封装（OpenAI 兼容协议）。"""

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: str = "",
        base_url: str = "https://api.deepseek.com/v1",
        temperature: float = 0.2,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature

    def chat(self, system: str, user: str) -> str:
        """返回文本；未安装依赖或调用失败抛异常（由调用方降级）。"""
        try:
            import litellm  # 延迟导入
        except ImportError as exc:
            raise ImportError("未安装 litellm：`pip install litellm`") from exc
        resp = litellm.completion(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content


def _provider_default() -> str:
    """provider：环境变量 > 配置 > deepseek（用于模型名前缀）。"""
    try:
        settings = load_settings()
        provider = os.getenv("LLM_PROVIDER") or settings.get("llm", {}).get("provider", "deepseek")
    except Exception:  # noqa: BLE001
        provider = "deepseek"
    return str(provider).strip().lower()


def _prefixed_model(model: str, provider: str) -> str:
    """裸模型名加 provider 前缀（deepseek-chat → deepseek/deepseek-chat）。

    litellm 对「裸模型名 + 自定义 base_url」会打印 Provider List 噪音警告；
    加前缀后按 provider 路由，行为一致且无警告。
    """
    model = (model or "").strip()
    if not model or "/" in model:
        return model or "deepseek-chat"
    return f"{provider}/{model}"


def llm_from_config(config: dict | None) -> LlmClient | None:
    """按配置字典构造 LLM 客户端（供按会话注入）；无 api_key 返回 None。"""
    if not config:
        return None
    api_key = config.get("api_key")
    if not api_key:
        return None
    provider = str(config.get("provider") or _provider_default()).strip().lower()
    try:
        return LlmClient(
            model=_prefixed_model(config.get("model") or "deepseek-chat", provider),
            api_key=api_key,
            base_url=config.get("base_url") or "https://api.deepseek.com/v1",
            temperature=float(config.get("temperature", 0.2)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 配置不可用：%s", exc)
        return None


def get_llm() -> LlmClient | None:
    """按环境变量构造 LLM 客户端；无 key 或不可用时返回 None（不阻塞分析）。

    先 load_settings()（内部会加载 .env），避免调用方未预加载 .env 时拿不到 key。
    """
    settings = load_settings()
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return None
    llm_cfg = settings.get("llm", {})
    return llm_from_config(
        {
            "model": os.getenv("LLM_MODEL") or llm_cfg.get("model", "deepseek-chat"),
            "api_key": api_key,
            "base_url": os.getenv("LLM_BASE_URL") or "https://api.deepseek.com/v1",
            "temperature": float(llm_cfg.get("temperature", 0.2)),
        }
    )
