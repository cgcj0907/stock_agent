/**
 * 把 LLM 返回的 JSON 文本解析为 TS 数据；容忍 ```json 代码块。
 * 非 JSON / 解析失败返回 null。
 */
export function tryParseJson(text: string): unknown | null {
  if (!text) return null;
  let t = text.trim();
  t = t.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  if (!/^[\{\[]/.test(t)) return null;
  try {
    return JSON.parse(t);
  } catch {
    return null;
  }
}
