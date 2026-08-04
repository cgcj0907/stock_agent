"""配置加载：config/*.yaml + 环境变量（YAML 缺失时用默认值）。"""
from __future__ import annotations

import os
from typing import Any

_DEFAULTS: dict[str, Any] = {
    "data_sources": {"primary": "mock"},  # mock | baostock | akshare
    "storage": {"backend": "sqlite", "path": "data/market.db"},
    "llm": {"provider": "deepseek", "model": "deepseek-chat", "temperature": 0.2},
    "monitor": {"schedule": "0 18 * * *", "channels": ["feishu", "wechat"]},
}


def _load_dotenv(path: str = ".env") -> None:
    """加载 .env（不覆盖已有环境变量；无第三方依赖）。"""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("\"'").strip()
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


def load_settings(path: str = "config/settings.yaml") -> dict[str, Any]:
    """读取 .env + 配置文件 + 环境变量覆盖；解析失败回退默认值。"""
    _load_dotenv()
    settings = {k: dict(v) if isinstance(v, dict) else v for k, v in _DEFAULTS.items()}
    try:
        import yaml  # type: ignore

        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        for k, v in loaded.items():
            if isinstance(v, dict) and isinstance(settings.get(k), dict):
                settings[k].update(v)
            else:
                settings[k] = v
    except (ImportError, FileNotFoundError, OSError):
        pass
    # 环境变量覆盖
    if os.getenv("DATABASE_URL"):
        settings["storage"] = {"backend": "postgres", "url": os.environ["DATABASE_URL"]}
    return settings
