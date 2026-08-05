export interface SourceLink {
  label: string;
  url: string;
}

/**
 * 根据 A 股代码生成「文章级」免费数据来源链接
 * （AkShare 底层：东方财富 F10 / 新浪财务指标 / 百度股市通估值 / 巨潮资讯披露）。
 * 仅支持 6 位数字代码；沪市以 6/9 开头，其余按深市处理。
 */
export function stockSourceLinks(code: string): SourceLink[] {
  const c = String(code ?? "").trim();
  if (!/^\d{6}$/.test(c)) return [];
  const market = c.startsWith("6") || c.startsWith("9") ? "sh" : "sz";
  const sym = `${market.toUpperCase()}${c}`;
  const year = new Date().getFullYear();
  return [
    {
      label: "东方财富 F10",
      url: `https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index?type=web&code=${sym}`,
    },
    {
      label: "新浪财务指标",
      url: `https://money.finance.sina.com.cn/corp/go.php/vFD_FinancialGuideLine/stockid/${c}/ctrl/${year}/displaytype/4.phtml`,
    },
    {
      label: "百度股市通",
      url: `https://gushitong.baidu.com/stock/ab-${c}`,
    },
    {
      label: "巨潮资讯",
      url: `https://www.cninfo.com.cn/new/disclosure/stock?stockCode=${c}`,
    },
  ];
}
