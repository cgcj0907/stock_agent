import { createClient } from "@/lib/supabase/server";
import { decryptSecret, maskSecret } from "@/lib/llm/crypto";
import type { LlmSetting } from "@/types/llm";

/** 服务端列出当前用户的 LLM 配置（脱敏 Key） */
export async function listLlmSettings(userId: string): Promise<LlmSetting[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("user_llm_settings")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: true });

  if (error) throw new Error(error.message);

  return (data ?? []).map((row) => {
    const plain = row.api_key_enc ? decryptSecret(row.api_key_enc) : "";
    const rest = { ...row } as Record<string, unknown>;
    delete rest.api_key_enc;
    return {
      ...rest,
      api_key_masked: plain ? maskSecret(plain) : null,
    } as LlmSetting;
  });
}
