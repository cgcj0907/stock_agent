import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { decryptSecret, encryptSecret, maskSecret } from "@/lib/llm/crypto";

const TABLE = "user_llm_settings";

function toPublic(row: {
  api_key_enc: string;
  [k: string]: unknown;
}) {
  const plain = row.api_key_enc ? decryptSecret(row.api_key_enc) : "";
  const rest = { ...row } as Record<string, unknown>;
  delete rest.api_key_enc;
  return { ...rest, api_key_masked: plain ? maskSecret(plain) : null };
}

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const supabase = await createClient();
  const { data, error } = await supabase
    .from(TABLE)
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ settings: (data ?? []).map(toPublic) });
}

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json();
  const provider = String(body.provider ?? "").trim();
  const base_url = String(body.base_url ?? "").trim();
  const model = String(body.model ?? "").trim();
  const api_key = String(body.api_key ?? "");
  const name = String(body.name ?? "").trim();

  if (!provider || !base_url || !model || !api_key) {
    return NextResponse.json(
      { error: "服务商、Base URL、模型与 API Key 均为必填" },
      { status: 400 }
    );
  }

  const supabase = await createClient();
  const is_default = !!body.is_default;
  if (is_default) {
    await supabase
      .from(TABLE)
      .update({ is_default: false })
      .eq("user_id", user.id);
  }

  const { data, error } = await supabase
    .from(TABLE)
    .insert({
      user_id: user.id,
      provider,
      name,
      base_url,
      model,
      api_key_enc: encryptSecret(api_key),
      is_default,
    })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ setting: toPublic(data) }, { status: 201 });
}
