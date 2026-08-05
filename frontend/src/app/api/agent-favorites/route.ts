import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";

const TABLE = "agent_favorites";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const supabase = await createClient();
  const { data, error } = await supabase
    .from(TABLE)
    .select("agent_id")
    .eq("user_id", user.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ agent_ids: (data ?? []).map((r) => r.agent_id) });
}

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = await req.json();
  const agent_id = String(body.agent_id ?? "");
  const favorite = !!body.favorite;
  if (!agent_id) {
    return NextResponse.json({ error: "缺少 agent_id" }, { status: 400 });
  }

  const supabase = await createClient();
  if (favorite) {
    const { error } = await supabase
      .from(TABLE)
      .upsert({ user_id: user.id, agent_id }, { onConflict: "user_id,agent_id" });
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  } else {
    const { error } = await supabase
      .from(TABLE)
      .delete()
      .eq("user_id", user.id)
      .eq("agent_id", agent_id);
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true, agent_id, favorite });
}
