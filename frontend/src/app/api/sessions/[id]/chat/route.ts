import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { backendAuthHeaders } from "@/lib/backend-auth";
import { decryptSecret } from "@/lib/llm/crypto";

type Params = { params: Promise<{ id: string }> };

/**
 * 追问对话（BFF）：按用户所选 LLM（或默认）在服务端解密后转发后端 chat，
 * 并把新消息同步到 Supabase messages。
 */
export async function POST(req: Request, { params }: Params) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const { id } = await params;
  const body = (await req.json()) as {
    content?: string;
    conversation_id?: string;
    llm_settings_id?: string;
  };
  if (!body.content?.trim()) {
    return NextResponse.json({ error: "消息不能为空" }, { status: 400 });
  }

  // 解析 LLM 配置：指定 llm_settings_id → 该配置；否则默认/最新
  let llm_config: Record<string, string> | undefined;
  try {
    const supabase = await createClient();
    const base = supabase
      .from("user_llm_settings")
      .select("*")
      .eq("user_id", user.id);
    const setting = body.llm_settings_id
      ? (await base.eq("id", body.llm_settings_id).maybeSingle()).data
      : (await base.eq("is_default", true).maybeSingle()).data ??
        (await base.order("created_at", { ascending: false }).limit(1)).data?.[0];
    if (setting?.api_key_enc) {
      llm_config = {
        provider: setting.provider,
        base_url: setting.base_url,
        model: setting.model,
        api_key: decryptSecret(setting.api_key_enc),
      };
    }
  } catch {
    // 未配置 → 后端用全局 LLM
  }

  const baseUrl =
    process.env.API_BASE_SERVER ||
    process.env.NEXT_PUBLIC_API_BASE ||
    "";
  if (!baseUrl) {
    return NextResponse.json(
      { error: "后端地址未配置（API_BASE_SERVER / NEXT_PUBLIC_API_BASE）" },
      { status: 500 }
    );
  }

  let res: Response;
  try {
    res = await fetch(`${baseUrl.replace(/\/+$/, "")}/api/sessions/${id}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(await backendAuthHeaders()),
      },
      body: JSON.stringify({ content: body.content, llm_config }),
      cache: "no-store",
      signal: AbortSignal.timeout(45000),
    });
  } catch (e) {
    const err = e as Error;
    return NextResponse.json(
      {
        error:
          err.name === "TimeoutError"
            ? "后端响应超时，请稍后重试"
            : `无法连接后端（${err.message}）`,
      },
      { status: 502 }
    );
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return NextResponse.json(
      { error: data.detail || data.error || `对话失败（${res.status}）` },
      { status: res.status }
    );
  }

  // 同步最新两条消息（user + assistant）到 Supabase
  const msgs: { role: string; content: string }[] =
    (data.messages ?? []).slice(-2);
  if (body.conversation_id && msgs.length) {
    try {
      const supabase = await createClient();
      const rows = msgs.map((m) => ({
        conversation_id: body.conversation_id,
        user_id: user.id,
        role: m.role,
        content: m.content,
      }));
      await supabase.from("messages").insert(rows);
    } catch (e) {
      console.error("[chat-sync] 同步消息到 Supabase 失败:", e);
    }
  }

  return NextResponse.json({ messages: msgs });
}
