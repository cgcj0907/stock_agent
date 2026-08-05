import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { decryptSecret } from "@/lib/llm/crypto";
import { testConnection } from "@/lib/llm/providers";

const TABLE = "user_llm_settings";

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json();

  let cfg: {
    provider: string;
    base_url: string;
    api_key?: string;
  };

  if (body.id) {
    const supabase = await createClient();
    const { data } = await supabase
      .from(TABLE)
      .select("*")
      .eq("id", body.id)
      .eq("user_id", user.id)
      .single();
    if (!data) {
      return NextResponse.json({ error: "配置不存在" }, { status: 404 });
    }
    cfg = {
      provider: data.provider,
      base_url: data.base_url,
      api_key: data.api_key_enc ? decryptSecret(data.api_key_enc) : "",
    };
  } else {
    cfg = {
      provider: String(body.provider ?? ""),
      base_url: String(body.base_url ?? "").trim(),
      api_key: String(body.api_key ?? ""),
    };
    if (!cfg.base_url) {
      return NextResponse.json(
        { error: "请先填写 Base URL" },
        { status: 400 }
      );
    }
  }

  const result = await testConnection(cfg);
  return NextResponse.json(result);
}
