"""M7 价格与情绪引擎：估值历史分位（10 年口径、winsorize 去异常）+ 股债性价比 + 情绪叠加。

格雷厄姆"市场先生"：价格（估值分位）是主锚，情绪（换手率等）只做叠加，
不改变"贵不贵"的判定，只影响同一估值下的置信度（过热降分、过冷加分）。

backlog 2026-08-07 落地：
- 7.6 主指标唯一事实来源：读 config/valuation_routing.yaml 的 primary_metric（代码兜底）。
- 7.7 10 年窗口精度：按自然年日历（today - N 年同日），不再用 365×N 天近似。
- 7.8 异常期剔除升级：winsorize 到 [1%, 99%]（样本 ≥30 时），小样本给降置信度不裁剪。
- 7.9 情绪叠加参数化：阈值/幅度读 config/scoring.yaml。
- 7.11 换手率口径细化：长期位置分位 + 近 short_window 期短期情绪分位，背离时提示。
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_SAMPLES = 10    # 分位计算最小样本数（不足则判"样本不足"）
WINDOW_YEARS = 10   # 估值分位口径：近 10 年（docs/01-design.md §3.7）
WINSORIZE_MIN = 30  # winsorize 生效的最小样本数（7.8）
WINSORIZE_FRAC = 0.01  # winsorize 到 [1%, 99%]

HOT_THRESHOLD = 0.66   # 情绪综合热度 ≥ 0.66 → 贪婪（默认，config 可覆盖）
COLD_THRESHOLD = 0.33  # 情绪综合热度 ≤ 0.33 → 恐惧
OVERLAY_HOT = -5.0     # 过热评分调整
OVERLAY_COLD = 5.0     # 过冷评分调整

# 换手率短期情绪窗口（7.11）：近 60 个交易日
SHORT_SENTIMENT_WINDOW = 60


def _load_routing_primary() -> dict[str, str]:
    """读 config/valuation_routing.yaml 的 primary_metric（7.6 唯一事实来源）。"""
    out: dict[str, str] = {}
    for path in (Path("config/valuation_routing.yaml"),
                 Path(__file__).resolve().parents[3] / "config" / "valuation_routing.yaml"):
        if not path.exists():
            continue
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for bt, meta in (raw.get("routing") or {}).items():
                pm = (meta or {}).get("primary_metric")
                if pm in ("pe", "pb", "null"):
                    out[bt] = pm
        except Exception as exc:  # noqa: BLE001
            logger.warning("valuation_routing.yaml 读取失败：%s", type(exc).__name__)
            continue
    return out


def _load_sentiment_params() -> dict[str, float]:
    """读 config/scoring.yaml 的 market_sentiment 参数（7.9），缺失回退默认。"""
    params: dict[str, float] = {}
    for path in (Path("config/scoring.yaml"),
                 Path(__file__).resolve().parents[3] / "config" / "scoring.yaml"):
        if not path.exists():
            continue
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            ms = raw.get("market_sentiment") or {}
            params = {k: float(v) for k, v in ms.items() if v is not None}
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("scoring.yaml 读取失败：%s", type(exc).__name__)
            continue
    return params


@dataclass
class MarketResult:
    pe_percentile: float | None
    pb_percentile: float | None
    position: str        # 极低估/低估/合理/高估/泡沫/样本不足
    score: float
    evidence: list[str] = field(default_factory=list)
    sentiment_heat: float | None = None  # 0~1，越高越热；None=未接入情绪指标


def _parse_date(value) -> datetime.date | None:
    """trade_date 解析：支持 YYYYMMDD 与 YYYY-MM-DD，非法返回 None。"""
    s = str(value or "").replace("-", "")
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _filter_window(records: list[dict], years: int = WINDOW_YEARS) -> list[dict]:
    """只保留最近 N 年的记录（7.7：自然年日历口径，today − N 年同日）。"""
    today = datetime.datetime.now(datetime.UTC).date()
    try:
        cutoff = today.replace(year=today.year - years)
    except ValueError:  # 2/29 → 非闰年，回退到 2/28
        cutoff = today.replace(year=today.year - years, day=28)
    return [r for r in records if (d := _parse_date(r.get("trade_date"))) is not None and d >= cutoff]


def _winsorize(history: list[float], frac: float = WINSORIZE_FRAC) -> list[float]:
    """winsorize 到 [frac, 1-frac] 分位（7.8）：极端值拉回分位边界而非删除。

    样本 < WINSORIZE_MIN 时不做裁剪（小样本给降置信度，见调用处）。
    """
    if len(history) < WINSORIZE_MIN:
        return list(history)
    s = sorted(history)
    n = len(s)
    lo_idx = max(0, int(n * frac) - 1)
    hi_idx = min(n - 1, int(n * (1 - frac)))
    lo, hi = s[lo_idx], s[hi_idx]
    return [min(max(v, lo), hi) for v in history]


def _trim(history: list[float], frac: float = WINSORIZE_FRAC) -> list[float]:
    """兼容旧名：等价于 winsorize（7.8 升级，保留旧函数名防回退）。"""
    return _winsorize(history, frac)


def _percentile(value: float, history: list[float]) -> float:
    """当前值在历史序列中的分位（≤当前值的占比，0~1）。"""
    if not history:
        return 0.0
    return sum(1.0 for v in history if v <= value) / len(history)


def _primary_metric(business_type: str | None, financial_subtype: str | None) -> str | None:
    """按生意类型选主估值指标（7.6：读 routing yaml 的 primary_metric，代码兜底）。

    - 金融细类覆盖：银行/券商 → PB，保险 → PE（比 routing 的 financial=null 更细）；
    - 未识别 → None（退化为 max(PE,PB) 保守口径）。
    """
    routing = _load_routing_primary()
    if business_type == "financial":
        if financial_subtype in ("bank", "broker"):
            return "pb"
        if financial_subtype == "insurance":
            return "pe"
    pm = routing.get(business_type or "")
    if pm == "pe":
        return "pe"
    if pm == "pb":
        return "pb"
    return None


def sentiment_from_daily(
    daily_records: list[dict],
    min_samples: int = MIN_SAMPLES,
    short_window: int = SHORT_SENTIMENT_WINDOW,
) -> dict | None:
    """从日线记录提炼情绪指标（7.11：长期位置分位 + 近 short_window 期短期情绪分位）。

    返回 {"metrics": {key: {"latest","percentile","note","unit"}}, "notes": [...]}；
    样本不足返回 None。
    """
    recs = sorted(
        (r for r in daily_records if r.get("trade_date") and r.get("turnover") is not None),
        key=lambda r: str(r["trade_date"]), reverse=True,
    )
    if len(recs) < min_samples:
        return None
    hist = [float(r["turnover"]) for r in recs]
    latest = hist[0]
    short_hist = hist[:short_window]
    metrics = {
        "turnover": {
            "latest": latest,
            "percentile": _percentile(latest, _winsorize(hist)),
            "note": "换手率（长期位置）",
            "unit": "%",
        },
    }
    notes: list[str] = []
    if len(short_hist) >= min_samples:
        short_pct = _percentile(latest, _winsorize(short_hist))
        metrics["turnover_short"] = {
            "latest": latest,
            "percentile": short_pct,
            "note": f"换手率（近 {len(short_hist)} 日短期情绪）",
            "unit": "%",
        }
        long_pct = metrics["turnover"]["percentile"]
        if abs(long_pct - short_pct) >= 0.25:
            direction = "短期更热（追涨）" if short_pct > long_pct else "短期更冷（恐慌）"
            notes.append(
                f"换手率长短背离：长期分位 {long_pct:.0%} vs 短期 {short_pct:.0%}（{direction}）"
            )
    return {"metrics": metrics, "notes": notes}


def _sentiment_overlay(
    heat: float | None,
    *,
    hot: float = HOT_THRESHOLD,
    cold: float = COLD_THRESHOLD,
    hot_amp: float = OVERLAY_HOT,
    cold_amp: float = OVERLAY_COLD,
) -> tuple[float, str]:
    """情绪叠加（7.9：阈值/幅度可参数化）：同一估值下市场越热分数越低（保守），越冷越高。"""
    if heat is None:
        return 0.0, "情绪指标未接入（换手率/北向/两融等），价格位置仅基于估值分位"
    if heat >= hot:
        return hot_amp, "市场情绪偏热（贪婪）"
    if heat <= cold:
        return cold_amp, "市场情绪偏冷（恐惧）"
    return 0.0, "市场情绪中性"


def assess_market(
    valuation_history: dict,
    risk_free: float = 0.04,
    business_type: str | None = None,
    financial_subtype: str | None = None,
    sentiment: dict | None = None,
    window_years: int = WINDOW_YEARS,
) -> MarketResult:
    sp = _load_sentiment_params()
    hot = sp.get("hot_threshold", HOT_THRESHOLD)
    cold = sp.get("cold_threshold", COLD_THRESHOLD)
    hot_amp = sp.get("overlay_hot", OVERLAY_HOT)
    cold_amp = sp.get("overlay_cold", OVERLAY_COLD)

    recs = sorted(
        _filter_window(
            (r for r in valuation_history.get("records", []) if r.get("trade_date")),
            years=window_years,
        ),
        key=lambda r: r["trade_date"], reverse=True,
    )
    pe_hist = [r["pe_ttm"] for r in recs if r.get("pe_ttm")]
    pb_hist = [r["pb"] for r in recs if r.get("pb")]
    latest_pe = pe_hist[0] if pe_hist else None
    latest_pb = pb_hist[0] if pb_hist else None
    latest_dv = next((r["dv_ttm"] for r in recs if r.get("dv_ttm")), None)

    evidence = [f"估值历史样本：近{window_years}年 PE {len(pe_hist)} 期 / PB {len(pb_hist)} 期"]

    pe_ok = len(pe_hist) >= MIN_SAMPLES and latest_pe is not None
    pb_ok = len(pb_hist) >= MIN_SAMPLES and latest_pb is not None

    if not pe_ok and not pb_ok:
        return MarketResult(
            pe_percentile=None, pb_percentile=None, position="样本不足（<10 期）",
            score=50.0,
            evidence=evidence + ["⚠️ 历史样本不足，分位与价格位置暂不可靠"],
        )

    pe_ref = _winsorize(pe_hist)
    pb_ref = _winsorize(pb_hist)
    pe_pct = _percentile(latest_pe, pe_ref) if pe_ok else None
    pb_pct = _percentile(latest_pb, pb_ref) if pb_ok else None
    if not pe_ok:
        # 银行/保险/资产型公司：PE 常失真或缺失，PB 更有效 → 不因缺 PE 误判"样本不足"
        evidence.append("⚠️ PE 历史样本不足，以 PB 分位判定价格位置（银行/资产型公司常见）")

    primary = _primary_metric(business_type, financial_subtype)
    if primary == "pb" and pb_pct is not None:
        anchor_pct, anchor_name = pb_pct, "PB"
    elif primary == "pe" and pe_pct is not None:
        anchor_pct, anchor_name = pe_pct, "PE"
    else:
        anchor_pct = max(p for p in (pe_pct, pb_pct) if p is not None)
        anchor_name = "max(PE,PB)"
    if primary is not None and ((primary == "pb" and pb_pct is None) or (primary == "pe" and pe_pct is None)):
        evidence.append(f"主指标 {primary.upper()} 样本不足，回退 {anchor_name} 判定")

    if anchor_pct < 0.2:
        position, score = "极低估", 95.0
    elif anchor_pct < 0.4:
        position, score = "低估", 80.0
    elif anchor_pct < 0.6:
        position, score = "合理", 60.0
    elif anchor_pct < 0.8:
        position, score = "高估", 30.0
    else:
        position, score = "泡沫", 10.0

    # 情绪叠加（只调置信度，不改价格位置）
    heat: float | None = None
    metrics = (sentiment or {}).get("metrics") or {}
    avail = {k: v for k, v in metrics.items() if v.get("percentile") is not None}
    if avail:
        heat = round(sum(v["percentile"] for v in avail.values()) / len(avail), 4)
        for k, v in avail.items():
            unit = v.get("unit", "")
            evidence.append(
                f"情绪：{v.get('note', k)} {v['latest']}{unit}（历史分位 {v['percentile']:.0%}）"
            )
    overlay, sentiment_note = _sentiment_overlay(heat, hot=hot, cold=cold, hot_amp=hot_amp, cold_amp=cold_amp)
    if heat is not None:
        evidence.append(f"情绪综合热度 {heat:.0%}（{sentiment_note}），评分 {'−' if overlay < 0 else '+'}{abs(overlay):.0f}")
    else:
        evidence.append(sentiment_note)
    if sentiment and sentiment.get("notes"):
        evidence.extend(sentiment["notes"])
    score = max(0.0, min(100.0, round(score + overlay)))

    ey = (1 / latest_pe if latest_pe and latest_pe > 0 else None) if pe_ok else None
    pct_parts = []
    if pe_pct is not None:
        pct_parts.append(f"PE(TTM) {latest_pe} 分位 {pe_pct:.0%}")
    if pb_pct is not None:
        pct_parts.append(f"PB {latest_pb} 分位 {pb_pct:.0%}")
    if primary:
        pct_parts.append(f"主指标 {anchor_name}")
    evidence += [
        "；".join(pct_parts),
        f"股债性价比：盈利收益率 {ey:.1%} vs 无风险利率 {risk_free:.1%}（{position}）" if ey else "盈利收益率不可计算（PE 样本不足）",
    ]
    if latest_dv is not None:
        evidence.append(f"股息率 {latest_dv:.1%} vs 无风险利率 {risk_free:.1%}（{'有吸引力' if latest_dv >= risk_free else '不占优'}）")
    evidence.append(f"价格位置：{position}（市场先生报价）")
    return MarketResult(
        pe_percentile=round(pe_pct, 4) if pe_pct is not None else None,
        pb_percentile=round(pb_pct, 4) if pb_pct is not None else None,
        position=position, score=score, evidence=evidence,
        sentiment_heat=heat,
    )
