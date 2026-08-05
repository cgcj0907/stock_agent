export interface SourceLink {
  label: string;
  url: string;
}

/**
 * 根据 A 股代码生成常用免费数据源链接（AkShare 底层：东方财富 / 新浪财经 / 巨潮资讯）。
 * 仅支持 6 位数字代码；沪市以 6 开头，其余按深市处理。
 */
export function stockSourceLinks(code: string): SourceLink[] {
  const c = String(code ?? "").trim();
  if (!/^\d{6}$/.test(c)) return [];
  const market = c.startsWith("6") ? "sh" : "sz";
  const sym = `${market}${c}`;
  return [
    { label: "东方财富", url: `https://quote.eastmoney.com/${market}${c}.html` },
    {
      label: "新浪财经",
      url: `https://finance.sina.com.cn/realstock/company/${sym}/nc.shtml`,
    },
    {
      label: "巨潮资讯",
      url: `https://www.cninfo.com.cn/new/fulltextSearch?keyWord=${c}`,
    },
  ];
}
