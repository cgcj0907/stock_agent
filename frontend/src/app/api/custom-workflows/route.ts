import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import type { CustomWorkflow } from "@/types/custom-workflow";

const TABLE = "custom_workflows";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const supabase = await createClient();
  const { data, error } = await supabase
    .from(TABLE)
    .select("*")
    .eq("user_id", user.id)
    .order("updated_at", { ascending: false });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ workflows: data ?? [] });
}

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  const body = (await req.json()) as {
    name?: string;
    description?: string;
    steps?: unknown[];
  };
  const name = String(body.name ?? "").trim();
  const description = String(body.description ?? "").trim();
  const steps = Array.isArray(body.steps) ? body.steps : [];

  if (!name) return NextResponse.json({ error: "请填写工作流名称" }, { status: 400 });
  if (steps.length === 0)
    return NextResponse.json({ error: "请至少添加一个智能体" }, { status: 400 });

  const supabase = await createClient();
  const { data, error } = await supabase
    .from(TABLE)
    .insert({ user_id: user.id, name, description, steps })
    .select()
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ workflow: data as CustomWorkflow }, { status: 201 });
}
