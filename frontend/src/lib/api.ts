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

/** 解析后端 SSE 事件流（支持 GET/POST，init 用于 POST 携带 body） */
export async function streamSse(
  url: string,
  onEvent: (event: Record<string, unknown>) => void,
  options?: { signal?: AbortSignal; init?: RequestInit }
): Promise<void> {
  const res = await fetch(url, {
    ...options?.init,
    cache: "no-store",
    signal: options?.signal,
  });
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

/** 通过 SSE 长链接运行会话并实时推送进度事件 */
export async function runSessionViaSse(
  sessionId: string,
  handlers: {
    /** 长链接已建立、后端开始执行（收到 started 事件） */
    onStarted?: () => void;
    onStep: (step: string, status: string) => void;
    /** LLM 流式增量（打字机数据源）：kind=content|thinking（思考过程单独灰字渲染） */
    onChunk?: (step: string, agent: string, kind: string, chunk: string) => void;
    onDone: (status: string) => void;
    onError: (message: string) => void;
  }
): Promise<void> {
  await streamSse(`${API_BASE}/api/sessions/${sessionId}/events`, (evt) => {
    if (evt.type === "started") {
      handlers.onStarted?.();
    } else if (evt.type === "step") {
      handlers.onStep(String(evt.step), String(evt.status));
    } else if (evt.type === "llm_chunk") {
      handlers.onChunk?.(
        String(evt.step),
        String(evt.agent ?? ""),
        String(evt.kind ?? "content"),
        String(evt.chunk ?? "")
      );
    } else if (evt.type === "done") {
      handlers.onDone(String(evt.status ?? "completed"));
    } else if (evt.type === "error") {
      handlers.onError(String(evt.message ?? "运行失败"));
    }
  });
}

/** 通过 SSE 观察已有会话进度，不触发重新执行 */
export async function watchSessionViaSse(
  sessionId: string,
  handlers: {
    onStarted?: () => void;
    onStep: (step: string, status: string) => void;
    /** watch 端点不推送 llm_chunk（增量不落库），保留接口以便将来支持 */
    onChunk?: (step: string, agent: string, kind: string, chunk: string) => void;
    onDone: (status: string) => void;
    onError: (message: string) => void;
    signal?: AbortSignal;
  }
): Promise<void> {
  await streamSse(
    `${API_BASE}/api/sessions/${sessionId}/watch`,
    (evt) => {
      if (evt.type === "started") {
        handlers.onStarted?.();
      } else if (evt.type === "step") {
        handlers.onStep(String(evt.step), String(evt.status));
      } else if (evt.type === "llm_chunk") {
        handlers.onChunk?.(
          String(evt.step),
          String(evt.agent ?? ""),
          String(evt.kind ?? "content"),
          String(evt.chunk ?? "")
        );
      } else if (evt.type === "done") {
        handlers.onDone(String(evt.status ?? "completed"));
      } else if (evt.type === "error") {
        handlers.onError(String(evt.message ?? "观察失败"));
      }
    },
    { signal: handlers.signal }
  );
}


/** 追问对话（流式版）：POST /chat/stream，SSE 实时推送 chat_chunk（kind=content|thinking），
 *  结尾 done（含完整回复）。assistant 消息由服务端在结束时落库。 */
export async function chatViaSse(
  sessionId: string,
  body: { content: string; llm_config?: Record<string, unknown> },
  handlers: {
    onChunk?: (kind: string, chunk: string) => void;
    onDone: (content: string) => void;
    onError: (message: string) => void;
  }
): Promise<void> {
  await streamSse(
    `${API_BASE}/api/sessions/${sessionId}/chat/stream`,
    (evt) => {
      if (evt.type === "chat_chunk") {
        handlers.onChunk?.(
          String(evt.kind ?? "content"),
          String(evt.chunk ?? "")
        );
      } else if (evt.type === "done") {
        handlers.onDone(String(evt.content ?? ""));
      } else if (evt.type === "error") {
        handlers.onError(String(evt.message ?? "对话失败"));
      }
    },
    {
      init: {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    }
  );
}
