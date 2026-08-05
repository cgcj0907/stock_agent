/** LLM 服务商预设（M2） */
export interface LlmProviderPreset {
  id: string;
  label: string;
  baseUrl: string;
  models: string[];
  keyPlaceholder: string;
  note?: string;
}

export const LLM_PROVIDERS: LlmProviderPreset[] = [
  {
    id: "deepseek",
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    models: ["deepseek-chat", "deepseek-reasoner"],
    keyPlaceholder: "sk-…",
    note: "性价比高，中文好，A 股分析推荐",
  },
  {
    id: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3-mini"],
    keyPlaceholder: "sk-…",
  },
  {
    id: "qwen",
    label: "通义千问 Qwen",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    models: ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
    keyPlaceholder: "sk-…",
    note: "阿里云 DashScope，OpenAI 兼容模式",
  },
  {
    id: "ollama",
    label: "Ollama（本地）",
    baseUrl: "http://localhost:11434",
    models: ["llama3.1", "qwen2.5", "deepseek-r1"],
    keyPlaceholder: "本地无需 Key，可留空",
    note: "本地/内网部署；Vercel 服务端测试需内网可达",
  },
  {
    id: "custom",
    label: "自定义（OpenAI 兼容）",
    baseUrl: "",
    models: [],
    keyPlaceholder: "sk-…",
    note: "任意 OpenAI 兼容接口",
  },
];

export function getProvider(id: string): LlmProviderPreset {
  return LLM_PROVIDERS.find((p) => p.id === id) ?? LLM_PROVIDERS[0];
}

/** 测试连通性：OpenAI 兼容用 GET /models；Ollama 用 GET /api/tags */
export async function testConnection(cfg: {
  provider: string;
  base_url: string;
  api_key?: string;
}): Promise<{ ok: boolean; message: string; latencyMs: number }> {
  const start = Date.now();
  const base = cfg.base_url.trim().replace(/\/+$/, "");
  if (!/^https?:\/\//.test(base)) {
    return { ok: false, message: "Base URL 需以 http(s):// 开头", latencyMs: 0 };
  }
  const url =
    cfg.provider === "ollama" ? `${base}/api/tags` : `${base}/models`;

  try {
    const res = await fetch(url, {
      headers: cfg.api_key
        ? { Authorization: `Bearer ${cfg.api_key}` }
        : undefined,
      signal: AbortSignal.timeout(15000),
      cache: "no-store",
    });
    const latencyMs = Date.now() - start;
    if (!res.ok) {
      const text = (await res.text()).slice(0, 200);
      return {
        ok: false,
        message: `HTTP ${res.status}${text ? `：${text}` : ""}`,
        latencyMs,
      };
    }
    return { ok: true, message: "连接成功", latencyMs };
  } catch (e) {
    const err = e as Error;
    return {
      ok: false,
      message: err.name === "TimeoutError" ? "连接超时（15s）" : err.message,
      latencyMs: Date.now() - start,
    };
  }
}
