import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { decryptSecret } from "@/lib/llm/crypto";

/**
 * 创建分析会话（BFF）：
 * 浏览器 → 本路由 → 附加用户默认 LLM 配置（服务端解密，Key 不落地浏览器）→ 后端。
 */
export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json();

  // 取用户默认 LLM 配置（无默认则取最新一条）；未配置则不带 llm_config
  let llm_config: Record<string, string> | undefined;
  try {
    const supabase = await createClient();
    const { data: def } = await supabase
      .from("user_llm_settings")
      .select("*")
      .eq("user_id", user.id)
      .eq("is_default", true)
      .maybeSingle();
    const setting =
      def ??
      (
        await supabase
          .from("user_llm_settings")
          .select("*")
          .eq("user_id", user.id)
          .order("created_at", { ascending: false })
          .limit(1)
      ).data?.[0];
    if (setting?.api_key_enc) {
      llm_config = {
        provider: setting.provider,
        base_url: setting.base_url,
        model: setting.model,
        api_key: decryptSecret(setting.api_key_enc),
      };
    }
  } catch {
    // user_llm_settings 表未创建 / 解密失败 → 不带配置，后端用全局 LLM
  }

  const base =
    process.env.API_BASE_SERVER ||
    process.env.NEXT_PUBLIC_API_BASE ||
    "http://127.0.0.1:8000";
  const res = await fetch(`${base.replace(/\/+$/, "")}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, llm_config }),
    cache: "no-store",
  });
  const data = await res.json();
  if (!res.ok) {
    return NextResponse.json(
      { error: data.detail || data.error || `创建会话失败（${res.status}）` },
      { status: res.status }
    );
  }
  return NextResponse.json(data, { status: 201 });
}
