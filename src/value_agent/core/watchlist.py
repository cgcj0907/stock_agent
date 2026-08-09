"""自选股池加载（供 CLI data / daily 任务共用）。"""
from __future__ import annotations

SAMPLE_CODES = ["600519", "300750", "000333", "600036", "601899"]


def load_watchlist() -> list[str]:
    """读取 config/watchlist.yaml 的自选股；无 pyyaml/文件时回退样本。"""
    try:
        import yaml  # type: ignore

        with open("config/watchlist.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [str(item["code"]) for item in data.get("watchlist", [])]
    except (ImportError, FileNotFoundError, KeyError, OSError):
        return SAMPLE_CODES
