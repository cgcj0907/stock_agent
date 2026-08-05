"""统一模块契约（方案 1：强约束标准版，见 docs/09-module-contracts.md）。

批次 A：契约常量、枚举、结构化风险信号、meta 校验。
逐模块 outputs 五段式（core_facts/qualitative/signals/handoff/meta）迁移见批次 B/C。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

# ---- 五段式 outputs 骨架（§2） ----
SCHEMA_VERSION = "1.0"
OUTPUT_KEYS = (
    "schema_version",
    "module_type",
    "core_facts",
    "qualitative",
    "signals",
    "handoff",
    "meta",
)


class ModuleType(str, enum.Enum):
    """模块语义分类：决定谁消费该模块输出。"""

    FACT = "fact"  # 事实/指标（M1-M7）
    RISK = "risk"  # 风险聚合（M9）
    DECISION = "decision"  # 裁决（M8/M10）
    MONITOR = "monitor"  # 监控规则（M11）


class Completeness(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(str, enum.Enum):
    """风险信号严重度（§4.2 signals[]）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReasonCode(str, enum.Enum):
    """统一降级原因枚举（§3）。"""

    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"  # 数据源无数据/字段缺失
    DATA_STALE = "DATA_STALE"  # 数据过旧
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"  # 未配置 LLM 或调用失败
    INPUT_MISSING = "INPUT_MISSING"  # 依赖模块 handoff 字段缺失
    OUT_OF_RANGE = "OUT_OF_RANGE"  # 数值超出合理区间（数据异常）
    DIV_ZERO = "DIV_ZERO"  # 除零/不可计算


class BusinessType(str, enum.Enum):
    """M1 生意类型 / M4 估值路由（与 config/valuation_routing.yaml 键对齐）。"""

    CONSUMER_MONOPOLY = "consumer_monopoly"
    GROWTH = "growth"
    CYCLICAL = "cyclical"
    FINANCIAL = "financial"
    ASSET_BASED = "asset_based"
    STABLE_DIVIDEND = "stable_dividend"


class MarketState(str, enum.Enum):
    """M7 市场状态 handoff。"""

    OVERHEATED = "overheated"
    NORMAL = "normal"
    COLD = "cold"
    INSUFFICIENT = "insufficient"


class MosState(str, enum.Enum):
    """M8 安全边际状态 handoff（替代中文 status 文案）。"""

    ATTRACTIVE = "attractive"  # 买入区间（安全边际充足）
    FAIR = "fair"  # 合理
    EXPENSIVE = "expensive"  # 高估
    UNAVAILABLE = "unavailable"  # 数据不足/降级


class ProsperityCode(str, enum.Enum):
    """M3 景气度 handoff（替代中文"上行/平稳/下行"）。"""

    UP = "up"
    FLAT = "flat"
    DOWN = "down"


# ---- 结构化风险信号对象（§4.2） ----
@dataclass
class RiskSignal:
    """统一风险信号 schema，供 M9 聚合 / M11 监控直接消费，不再字符串转义。"""

    code: str  # 稳定信号码，如 OCF_NP_DIVERGENCE
    severity: str  # Severity 枚举值
    metric: str  # 相关指标名
    message: str  # 给人看的说明
    evidence: str = ""  # 证据（来源模块/期间）

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "metric": self.metric,
            "message": self.message,
            "evidence": self.evidence,
        }


def validate_signal(sig: dict | RiskSignal) -> list[str]:
    """返回校验错误列表；空列表=合法。"""
    d = sig.to_dict() if isinstance(sig, RiskSignal) else sig
    errors: list[str] = []
    for key in ("code", "severity", "metric", "message"):
        if not d.get(key):
            errors.append(f"signal 缺少字段: {key}")
    if d.get("severity") and d["severity"] not in {s.value for s in Severity}:
        errors.append(f"severity 非法: {d['severity']}（可选: {[s.value for s in Severity]}）")
    return errors


def is_valid_signal(sig: dict | RiskSignal) -> bool:
    return not validate_signal(sig)


# ---- meta 质量元数据（§2/§3） ----
def default_meta() -> dict:
    """模块未产生结果时的默认 meta（工作流/前端据此判断质量）。"""
    return {
        "confidence": 0.0,
        "completeness": Completeness.LOW.value,
        "degraded": False,
        "reason_codes": [],
    }


def build_meta(
    confidence: float,
    completeness: str = Completeness.LOW.value,
    degraded: bool = False,
    reason_codes: list[str] | None = None,
) -> dict:
    """构造合法 meta：confidence 夹逼到 [0,1]，枚举非法时回落默认。"""
    return {
        "confidence": round(max(0.0, min(1.0, float(confidence))), 3),
        "completeness": (
            completeness
            if completeness in {c.value for c in Completeness}
            else Completeness.LOW.value
        ),
        "degraded": bool(degraded),
        "reason_codes": [str(c) for c in (reason_codes or [])],
    }


def validate_meta(meta: dict | None) -> list[str]:
    """返回校验错误列表；空列表=合法（meta=None 视为未提供，不算错误）。"""
    if meta is None:
        return []
    errors: list[str] = []
    for key in ("confidence", "completeness", "degraded", "reason_codes"):
        if key not in meta:
            errors.append(f"meta 缺少字段: {key}")
    if "confidence" in meta:
        try:
            if not (0.0 <= float(meta["confidence"]) <= 1.0):
                errors.append("confidence 必须在 [0,1]")
        except (TypeError, ValueError):
            errors.append("confidence 必须为数值")
    if "completeness" in meta and meta["completeness"] not in {
        c.value for c in Completeness
    }:
        errors.append(f"completeness 非法: {meta['completeness']}")
    if "reason_codes" in meta:
        valid = {r.value for r in ReasonCode}
        bad = [c for c in meta["reason_codes"] if c not in valid]
        if bad:
            errors.append(f"reason_codes 含未注册枚举: {bad}（可选: {sorted(valid)}）")
    return errors


def is_valid_meta(meta: dict | None) -> bool:
    return not validate_meta(meta)
