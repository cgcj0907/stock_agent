"""校准 A/B 分析（docs/12-v2-upgrade.md §8）：规则分 vs 规则+校准 v2 的区分度对比。

数据源：
- 校准轨迹语料：会话里的 ModuleResult.calibration（P2 落库）
  {module_id, base, final, outcome, delta, ...}，base=规则分、final=校准后实际分；
- 前向收益：daily_price 序列，as_of 后 FORWARD_MONTHS 的前向收益。

输出：每模块 A/B 指标（相关 / 档位翻转 / 偏置 / 结果分布）+ 数据驱动建议（enabled/cap）。
判断逻辑（docs/12-v2-upgrade.md §8.2）：
- 校准区分度下降（calib_corr < rule_corr - CORR_GAIN_MIN）→ 建议 enabled: false；
- 平均 |delta| 偏大（饱和）→ 建议收紧 cap；
- 平均 delta 系统性偏置 → 建议提示词校准或收紧；
- 样本不足 → 保持现状。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from value_agent.sessions.models import Session

# 前向收益窗口（月）
FORWARD_MONTHS = 6
# 建议阈值（数据驱动开关，见 §8.2）
MIN_SAMPLES = 10          # 少于该样本数 → 不下结论，保持现状
CORR_GAIN_MIN = 0.05      # 校准相关必须比规则高这么多才认为「有增益」
CAP_SATURATION_DELTA = 8.0  # 平均 |delta| 超过 → 建议收紧 cap
BIAS_TOL = 3.0            # 平均 delta 超过 → 提示系统性偏置
BAND_THRESHOLDS = (80.0, 65.0, 50.0)

# 只有真正参与评分流程的样本才进相关分析（disabled=无 LLM/禁用，不构成校准尝试）
_ACTIVE_OUTCOMES = {"applied", "capped", "band_protected",
                    "rejected_no_evidence", "rejected_no_reason", "fallback"}


@dataclass
class CalibrationSample:
    """一个（公司 × 模块 × 时点）的校准样本。"""

    code: str
    module_id: str
    as_of: str          # 分析日 YYYYMMDD（session.created_at）
    base: float         # 规则分（反事实：不校准会用这个分）
    final: float        # 校准后实际分
    outcome: str
    delta: float | None = None
    forward: float | None = None  # 前向收益（脚本回填）


@dataclass
class ModuleAbReport:
    """单模块 A/B 报告。"""

    module_id: str
    n: int
    rule_corr: float | None = None
    calib_corr: float | None = None
    corr_gain: float | None = None  # calib_corr - rule_corr（>0 校准有增益）
    band_flip_rate: float = 0.0
    up_flips: int = 0
    down_flips: int = 0
    mean_delta: float = 0.0
    mean_abs_delta: float = 0.0
    outcome_counts: dict = field(default_factory=dict)
    recommendation: str = ""


# ---------- 抽取 ----------


def extract_samples(sessions: list[Session]) -> list[CalibrationSample]:
    """从会话语料里抽取每模块校准样本（跳过未校准的 disabled 轨迹）。"""
    out: list[CalibrationSample] = []
    for session in sessions:
        if session.created_at is None:
            continue
        as_of = session.created_at.strftime("%Y%m%d")
        for r in session.module_results.values():
            cal = r.calibration or {}
            if not isinstance(cal, dict) or cal.get("outcome") not in _ACTIVE_OUTCOMES:
                continue
            base = cal.get("base")
            final = cal.get("final")
            if not isinstance(base, (int, float)) or not isinstance(final, (int, float)):
                continue
            out.append(CalibrationSample(
                code=session.company_code,
                module_id=cal.get("module_id") or r.module,
                as_of=as_of,
                base=float(base),
                final=float(final),
                outcome=str(cal.get("outcome")),
                delta=cal.get("delta"),
            ))
    return out


# ---------- 前向收益 ----------


def add_months(as_of: str, months: int) -> str:
    """YYYYMMDD 加 N 个月（日归 01，用于取整月窗口）。"""
    y, m = int(as_of[:4]), int(as_of[4:6])
    m += months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}{m:02d}01"


def forward_return(daily: list[dict], as_of: str, months: int = FORWARD_MONTHS) -> float | None:
    """as_of 后 months 个月的前向收益（sell/buy - 1）；窗口内数据不足返回 None。"""
    recs = [r for r in daily if str(r.get("trade_date", "")) >= str(as_of)]
    if not recs:
        return None
    buy = min(recs, key=lambda r: str(r["trade_date"]))["close"]
    end = add_months(as_of, months)
    future = [r for r in recs if str(r.get("trade_date", "")) <= end]
    if not future:
        return None
    sell = max(future, key=lambda r: str(r["trade_date"]))["close"]
    # 覆盖度不足（可用窗口 < 目标窗口一半）→ 前向收益不可靠，视为缺失
    last_date = str(max(future, key=lambda r: str(r["trade_date"]))["trade_date"])
    span_months = (int(last_date[:4]) - int(as_of[:4])) * 12 + (int(last_date[4:6]) - int(as_of[4:6]))
    if span_months < months / 2:
        return None
    if buy and sell and buy > 0:
        return round(sell / buy - 1, 4)
    return None


# ---------- 统计 ----------


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """纯 Python 斯皮尔曼秩相关（无 scipy 依赖）；n<3 或常数序列返回 None。"""
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return round(cov / (vx * vy) ** 0.5, 3)


def band_of(score: float) -> int:
    """分数所在档位下标（80/65/50）。"""
    for i, thr in enumerate(BAND_THRESHOLDS):
        if score >= thr:
            return i
    return len(BAND_THRESHOLDS)


def _recommend(rep: ModuleAbReport) -> str:
    """数据驱动开关（§8.2）：每模块 enabled/cap 建议。"""
    if rep.n < MIN_SAMPLES:
        return f"样本不足（n={rep.n} < {MIN_SAMPLES}），保持现状"
    if (rep.corr_gain is not None and rep.rule_corr is not None and rep.calib_corr is not None
            and rep.corr_gain < -CORR_GAIN_MIN):
        return f"校准区分度下降（{rep.corr_gain:+.2f}）→ 建议 enabled: false"
    if rep.mean_abs_delta > CAP_SATURATION_DELTA:
        return f"平均 |delta|={rep.mean_abs_delta:.1f} 偏大 → 建议收紧 cap"
    if abs(rep.mean_delta) > BIAS_TOL:
        direction = "偏高" if rep.mean_delta > 0 else "偏低"
        return f"系统性偏{direction}（mean delta {rep.mean_delta:+.1f}）→ 建议提示词校准/收紧"
    return "校准有增益或中性，保持现状"


def analyze(samples: list[CalibrationSample]) -> dict[str, ModuleAbReport]:
    """按模块聚合 A/B 指标。"""
    by_module: dict[str, list[CalibrationSample]] = {}
    for s in samples:
        by_module.setdefault(s.module_id, []).append(s)

    reports: dict[str, ModuleAbReport] = {}
    for module_id, group in sorted(by_module.items()):
        with_fwd = [s for s in group if s.forward is not None]
        rule_corr = calib_corr = None
        if len(with_fwd) >= 3:
            rule_corr = spearman([s.base for s in with_fwd], [s.forward for s in with_fwd])
            calib_corr = spearman([s.final for s in with_fwd], [s.forward for s in with_fwd])
        corr_gain = None
        if rule_corr is not None and calib_corr is not None:
            corr_gain = round(calib_corr - rule_corr, 3)

        moved = [s for s in group if s.outcome in ("applied", "capped") and s.final != s.base]
        flips = [s for s in moved if band_of(s.base) != band_of(s.final)]
        up_flips = sum(1 for s in flips if s.final > s.base)
        down_flips = len(flips) - up_flips

        deltas = [s.delta for s in group if isinstance(s.delta, (int, float))]
        mean_delta = statistics.mean(deltas) if deltas else 0.0
        mean_abs_delta = statistics.mean([abs(d) for d in deltas]) if deltas else 0.0

        rep = ModuleAbReport(
            module_id=module_id,
            n=len(group),
            rule_corr=rule_corr,
            calib_corr=calib_corr,
            corr_gain=corr_gain,
            band_flip_rate=round(len(flips) / len(moved), 3) if moved else 0.0,
            up_flips=up_flips,
            down_flips=down_flips,
            mean_delta=round(mean_delta, 2),
            mean_abs_delta=round(mean_abs_delta, 2),
            outcome_counts={k: sum(1 for s in group if s.outcome == k) for k in sorted({s.outcome for s in group})},
        )
        rep.recommendation = _recommend(rep)
        reports[module_id] = rep
    return reports


def suggest_config(reports: dict[str, ModuleAbReport]) -> dict[str, dict]:
    """数据驱动的 llm_calibration.yaml 建议（只列需要改动的模块）。"""
    suggested: dict[str, dict] = {}
    for module_id, rep in reports.items():
        if rep.n < MIN_SAMPLES:
            continue
        if rep.corr_gain is not None and rep.corr_gain < -CORR_GAIN_MIN:
            suggested[module_id] = {"enabled": False}
        elif rep.mean_abs_delta > CAP_SATURATION_DELTA:
            suggested[module_id] = {"cap": max(5.0, round(rep.mean_abs_delta, 1))}
    return suggested
