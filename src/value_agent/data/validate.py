"""数据勾稽校验 + quality_flag（docs/01-design.md §3.3）。

校验失败的记录由 ETL 在入库前剔除并记录（不进分析）。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationReport:
    total: int
    valid: int = 0
    issues: list[dict] = field(default_factory=list)  # {index, rule, message}

    @property
    def invalid(self) -> int:
        return self.total - self.valid


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and v == v  # NaN 排除


def _check_date(value) -> bool:
    return isinstance(value, str) and value.isdigit() and len(value) == 8


def validate_financials(records: list[dict]) -> ValidationReport:
    """财务记录勾稽：日期格式 / ROE / 毛利率 / 负债率 / EPS / 现金流比。"""
    report = ValidationReport(total=len(records))
    for i, r in enumerate(records):
        bad = []
        if not _check_date(r.get("period")):
            bad.append("period 非 YYYYMMDD")
        for key, lo, hi in (("roe", -100, 100), ("grossprofit_margin", 0, 100),
                            ("netprofit_margin", -100, 100), ("ocf_to_np", -100, 100)):
            v = r.get(key)
            if v is not None and (not _is_num(v) or not (lo <= v <= hi)):
                bad.append(f"{key} 越界({lo}~{hi})")
        v = r.get("debt_to_assets")
        if v is not None and (not _is_num(v) or not (0 <= v <= 1.5)):
            bad.append("debt_to_assets 越界(0~1.5)")
        v = r.get("eps")
        if v is not None and (not _is_num(v) or abs(v) > 10000):
            bad.append("eps 异常")
        if bad:
            report.issues.append({"index": i, "rule": "financials", "message": "; ".join(bad)})
        else:
            report.valid += 1
    return report


def validate_daily_prices(records: list[dict]) -> ValidationReport:
    """行情勾稽：日期 / 正价格 / 最高≥最低、收盘在区间内。"""
    report = ValidationReport(total=len(records))
    for i, r in enumerate(records):
        bad = []
        if not _check_date(r.get("trade_date")):
            bad.append("trade_date 非 YYYYMMDD")
        close = r.get("close")
        if close is None or not _is_num(close) or close <= 0:
            bad.append("close 非正数")
        else:
            high, low = r.get("high"), r.get("low")
            if high is not None and _is_num(high) and high < max(r.get("open", close), close, low if _is_num(low) else close):
                bad.append("high 小于最高价")
            if low is not None and _is_num(low) and low > min(r.get("open", close), close, high if _is_num(high) else close):
                bad.append("low 大于最低价")
        v = r.get("volume")
        if v is not None and (not _is_num(v) or v < 0):
            bad.append("volume 为负")
        if bad:
            report.issues.append({"index": i, "rule": "daily_price", "message": "; ".join(bad)})
        else:
            report.valid += 1
    return report


def validate_valuation_history(records: list[dict]) -> ValidationReport:
    """估值记录：日期 / PB/股息率非负 / PE 允许为负（亏损）。"""
    report = ValidationReport(total=len(records))
    for i, r in enumerate(records):
        bad = []
        if not _check_date(r.get("trade_date")):
            bad.append("trade_date 非 YYYYMMDD")
        for key in ("pb", "dv_ttm"):
            v = r.get(key)
            if v is not None and (not _is_num(v) or v < 0):
                bad.append(f"{key} 为负")
        if bad:
            report.issues.append({"index": i, "rule": "valuation_history", "message": "; ".join(bad)})
        else:
            report.valid += 1
    return report


def validate_dividends(records: list[dict]) -> ValidationReport:
    report = ValidationReport(total=len(records))
    for i, r in enumerate(records):
        bad = []
        if not _check_date(r.get("period")):
            bad.append("period 非 YYYYMMDD")
        v = r.get("cash_div_tax")
        if v is not None and (not _is_num(v) or v < 0):
            bad.append("cash_div_tax 为负")
        if bad:
            report.issues.append({"index": i, "rule": "dividends", "message": "; ".join(bad)})
        else:
            report.valid += 1
    return report


VALIDATORS = {
    "financials": validate_financials,
    "daily_price": validate_daily_prices,
    "valuation_history": validate_valuation_history,
    "dividends": validate_dividends,
}


def validate_table(table: str, records: list[dict]) -> ValidationReport:
    fn = VALIDATORS.get(table)
    return fn(records) if fn else ValidationReport(total=len(records), valid=len(records))


def valid_records(table: str, records: list[dict]) -> tuple[list[dict], ValidationReport]:
    """返回 (有效记录, 校验报告)；company 表跳过校验。"""
    if table == "company":
        return records, ValidationReport(total=len(records), valid=len(records))
    report = validate_table(table, records)
    invalid_idx = {iss["index"] for iss in report.issues}
    valid = [r for i, r in enumerate(records) if i not in invalid_idx]
    return valid, report
