import { redirect } from "next/navigation";

import { LlmSettingsClient } from "./llm-settings-client";
import { listLlmSettings } from "@/lib/llm/settings";
import { getCurrentUser } from "@/lib/supabase/auth";

export default async function LlmSettingsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  let settings: Awaited<ReturnType<typeof listLlmSettings>> = [];
  try {
    settings = await listLlmSettings(user.id);
  } catch {
    // 表尚未创建时静默降级为空列表（页面会提示添加）
  }

  return <LlmSettingsClient initialSettings={settings} />;
}
