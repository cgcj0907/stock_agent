"""LLM 客户端（可选）：统一接入 DeepSeek/Qwen/OpenAI/本地，未配置 key 则返回 None。

设计：分析以规则引擎为主，LLM 只做定性补充；无 LLM 时模块仍可运行（降级为规则结果）。
"""
from __future__ import annotations

import logging
import os

from value_agent.core.config import load_settings

logger = logging.getLogger(__name__)


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


def get_llm() -> LlmClient | None:
    """按环境变量构造 LLM 客户端；无 key 或不可用时返回 None（不阻塞分析）。"""
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return None
    settings = load_settings()
    llm_cfg = settings.get("llm", {})
    try:
        return LlmClient(
            model=os.getenv("LLM_MODEL") or llm_cfg.get("model", "deepseek-chat"),
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL") or "https://api.deepseek.com/v1",
            temperature=float(llm_cfg.get("temperature", 0.2)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 不可用：%s", exc)
        return None
