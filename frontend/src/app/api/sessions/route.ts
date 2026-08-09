import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { backendAuthHeaders } from "@/lib/backend-auth";
import { decryptSecret } from "@/lib/llm/crypto";

/** 宽松上限：Render 免费版冷启动可能较慢（Vercel Hobby 上限 60s） */
export const maxDuration = 60;

/**
 * 创建分析会话（BFF）：
 * 浏览器 → 本路由 → 附加用户默认 LLM 配置（服务端解密，Key 不落地浏览器）→ 后端。
 */
export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json();

  // M0 投资者画像（可选，docs/13）：仅当工作流包含 M0 步骤时，服务端附加画像快照（按需发送）。
  // 剔除身份字段（display_name/email/avatar/时间戳），后端落库/进 LLM 前还会再剥离一次。
  const wantsProfile =
    Array.isArray(body.workflow_steps) &&
    body.workflow_steps.some(
      (s: { agent?: string } | null | undefined) => s?.agent === "M0_investor_profile"
    );
  let investor_profile: Record<string, unknown> | undefined;
  if (wantsProfile) {
    try {
      const supabase = await createClient();
      const { data } = await supabase
        .from("profiles")
        .select("*")
        .eq("id", user.id)
        .maybeSingle();
      if (data) {
        const { display_name, email, avatar_path, avatar_url, created_at, updated_at, ...rest } =
          data as Record<string, unknown>;
        void display_name;
        void email;
        void avatar_path;
        void avatar_url;
        void created_at;
        void updated_at;
        investor_profile = rest;
      }
    } catch {
      // 画像读取失败 → 不带（后端 M0 中性兜底，不影响分析）
    }
  }

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
    "";
  if (!base) {
    return NextResponse.json(
      {
        error:
          "后端地址未配置：请在 Vercel 环境变量设置 API_BASE_SERVER（或 NEXT_PUBLIC_API_BASE）为后端地址",
      },
      { status: 500 }
    );
  }

  let res: Response;
  try {
    res = await fetch(`${base.replace(/\/+$/, "")}/api/sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(await backendAuthHeaders()),
      },
      body: JSON.stringify({
        ...body,
        llm_config,
        ...(investor_profile ? { investor_profile } : {}),
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(45000),
    });
  } catch (e) {
    const err = e as Error;
    const msg =
      err.name === "TimeoutError"
        ? "后端响应超时（Render 免费版可能正在冷启动，请稍后重试）"
        : `无法连接后端（${err.message}）`;
    return NextResponse.json({ error: msg }, { status: 502 });
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return NextResponse.json(
      { error: data.detail || data.error || `创建会话失败（${res.status}）` },
      { status: res.status }
    );
  }
  return NextResponse.json(data, { status: 201 });
}
