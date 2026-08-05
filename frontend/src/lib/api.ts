/** 后端 API 基础地址（浏览器直连；SSE 与普通 API 均走这里） */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function api<T = unknown>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const j = JSON.parse(text);
      detail = j.detail || j.error || text;
    } catch {
      // ignore
    }
    throw new Error(detail || `请求失败（${res.status}）`);
  }
  return res.json() as Promise<T>;
}

/** 解析后端 SSE 事件流 */
export async function streamSse(
  url: string,
  onEvent: (event: Record<string, unknown>) => void
): Promise<void> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok || !res.body) {
    throw new Error(`SSE 连接失败（${res.status}）`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const dataLine = part
        .split("\n")
        .find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      try {
        onEvent(JSON.parse(dataLine.slice(5).trim()));
      } catch {
        // 忽略无法解析的事件
      }
    }
  }
}
