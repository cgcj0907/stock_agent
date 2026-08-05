import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { decryptSecret, encryptSecret, maskSecret } from "@/lib/llm/crypto";

const TABLE = "user_llm_settings";

function toPublic(row: { api_key_enc: string; [k: string]: unknown }) {
  const plain = row.api_key_enc ? decryptSecret(row.api_key_enc) : "";
  const rest = { ...row } as Record<string, unknown>;
  delete rest.api_key_enc;
  return { ...rest, api_key_masked: plain ? maskSecret(plain) : null };
}

type Params = { params: Promise<{ id: string }> };

async function loadOwned(id: string, userId: string) {
  const supabase = await createClient();
  const { data } = await supabase
    .from(TABLE)
    .select("*")
    .eq("id", id)
    .eq("user_id", userId)
    .single();
  return { supabase, row: data };
}

export async function PATCH(req: Request, { params }: Params) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const { id } = await params;
  const { supabase, row } = await loadOwned(id, user.id);
  if (!row) return NextResponse.json({ error: "配置不存在" }, { status: 404 });

  const body = await req.json();
  const patch: Record<string, unknown> = {
    updated_at: new Date().toISOString(),
  };
  if (body.provider !== undefined) patch.provider = String(body.provider);
  if (body.name !== undefined) patch.name = String(body.name);
  if (body.base_url !== undefined)
    patch.base_url = String(body.base_url).trim();
  if (body.model !== undefined) patch.model = String(body.model).trim();
  if (body.api_key) patch.api_key_enc = encryptSecret(String(body.api_key));
  if (body.is_default !== undefined) patch.is_default = !!body.is_default;

  if (patch.is_default) {
    await supabase
      .from(TABLE)
      .update({ is_default: false })
      .eq("user_id", user.id)
      .neq("id", id);
  }

  const { data, error } = await supabase
    .from(TABLE)
    .update(patch)
    .eq("id", id)
    .select()
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ setting: toPublic(data) });
}

export async function DELETE(_req: Request, { params }: Params) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const { id } = await params;
  const { supabase, row } = await loadOwned(id, user.id);
  if (!row) return NextResponse.json({ error: "配置不存在" }, { status: 404 });

  const { error } = await supabase.from(TABLE).delete().eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ deleted: id });
}
