"""M1 商业模式认知引擎：生意类型分类 + 能力圈评级（确定性规则）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from value_agent.financials.quality import latest_annual

FINANCIAL_KEYWORDS = ["银行", "保险", "证券", "金融", "信托"]
CYCLICAL_KEYWORDS = [
    "有色", "钢铁", "煤炭", "化工", "石油", "航运", "水运", "海运", "运输",
    "房地产", "港口", "建材", "水泥", "机械", "汽车", "船舶", "造船",
]
ASSET_KEYWORDS = ["高速公路"]
# 公用事业/类债资产：稳定现金流 + 低成长 + 分红，应走高分红稳定（DDM），而非 DCF/唐朝 25 倍
UTILITY_KEYWORDS = ["电力", "水电", "燃气", "水务", "供热", "公用事业"]

TYPE_LABEL = {
    "consumer_monopoly": "消费垄断（高毛利/高ROE/低杠杆）",
    "growth": "成长",
    "cyclical": "周期",
    "financial": "金融",
    "asset_based": "资产型",
    "stable_dividend": "高分红稳定",
}

UNDERSTAND = {
    "consumer_monopoly": "能力圈内（模式直观）",
    "growth": "能力圈内（看增长与赛道）",
    "cyclical": "边缘（需行业周期专识）",
    "financial": "边缘（需专业会计与监管知识）",
    "asset_based": "边缘（需资产质量判断）",
    "stable_dividend": "能力圈内（看分红与现金流）",
}


@dataclass
class BusinessModelResult:
    business_type: str
    one_liner: str
    understandability: str
    industry: str
    score: float
    evidence: list[str] = field(default_factory=list)
    financial_subtype: str = "other"  # 金融细类：bank | broker | insurance | other（M4 用）


BUSINESS_TYPE_ALIASES = {
    "consumer_monopoly": "consumer_monopoly",
    "消费垄断": "consumer_monopoly",
    "growth": "growth",
    "成长": "growth",
    "cyclical": "cyclical",
    "周期": "cyclical",
    "financial": "financial",
    "金融": "financial",
    "asset_based": "asset_based",
    "资产型": "asset_based",
    "stable_dividend": "stable_dividend",
    "高分红稳定": "stable_dividend",
}


def financial_subtype_of(industry: str) -> str:
    """金融细类（M4 估值方法路由的依据）：银行走 PB-ROE，券商走正常化盈利+PB，保险暂用相对PE+DDM。"""
    if "银行" in industry:
        return "bank"
    if "证券" in industry:
        return "broker"
    if "保险" in industry:
        return "insurance"
    return "other"


def normalize_business_type(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower()
    return BUSINESS_TYPE_ALIASES.get(key) or BUSINESS_TYPE_ALIASES.get(value.strip())


def classify_business_type(
    industry: str, roe: float | None, gross_margin: float | None, debt: float | None
) -> str:
    """规则分类（M4 估值方法路由的依据）。"""
    if any(k in industry for k in FINANCIAL_KEYWORDS):
        return "financial"
    # 周期类先于资产类匹配：航运港口/港口这类重资产但强周期行业按周期处理
    if any(k in industry for k in CYCLICAL_KEYWORDS):
        return "cyclical"
    if any(k in industry for k in ASSET_KEYWORDS):
        return "asset_based"
    # 公用事业：类债资产，先于 ROE/毛利率启发式（长江电力这类会被误分消费垄断）
    if any(k in industry for k in UTILITY_KEYWORDS):
        return "stable_dividend"
    if (
        roe is not None and roe >= 15
        and gross_margin is not None and gross_margin >= 40
        and (debt is None or debt <= 0.5)
    ):
        return "consumer_monopoly"
    if roe is not None and roe >= 10:
        return "growth"
    return "cyclical"  # 未知行业保守按周期（估值禁用 DCF/唐朝）


def analyze_business_model(
    company_info: dict, financials: dict, *, business_type: str | None = None
) -> BusinessModelResult:
    recs = [r for r in financials.get("records", []) if r.get("period")]
    industry = company_info.get("industry", "")
    roe = latest_annual(recs, "roe")               # 年度口径（无行业信息时靠它分类）
    gm = latest_annual(recs, "grossprofit_margin")
    debt = latest_annual(recs, "debt_to_assets")

    rule_btype = classify_business_type(industry or "", roe, gm, debt)
    btype = normalize_business_type(business_type) or rule_btype
    financial_subtype = financial_subtype_of(industry or "")
    one_liner = f"{company_info.get('name', company_info.get('code'))}：{industry or '未知行业'}，{TYPE_LABEL[btype]}型生意"
    und = UNDERSTAND[btype]
    # 评分：数据完整度 + 简单性
    score = 60.0
    if industry:
        score += 15
    if roe is not None and gm is not None:
        score += 15
    if btype in ("consumer_monopoly", "growth", "stable_dividend"):
        score += 10
    score = min(100.0, score)

    evidence = [
        f"行业：{industry or '未知'}；ROE {roe}%；毛利率 {gm}%；资产负债率 {debt}",
        f"生意类型：{btype}（{TYPE_LABEL[btype]}）—— M4 估值方法将按此路由",
        f"可理解性：{und}",
    ]
    if btype != rule_btype:
        evidence.append(f"规则分类参考：{rule_btype}（{TYPE_LABEL[rule_btype]}）")
    return BusinessModelResult(
        business_type=btype, one_liner=one_liner,
        financial_subtype=financial_subtype,
        understandability=und, industry=industry, score=round(score, 1),
        evidence=evidence,
    )
