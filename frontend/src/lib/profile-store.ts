import { createClient } from "@/lib/supabase/server";
import {
  EMPTY_PROFILE,
  mergeProfileRecord,
  normalizeProfileInput,
  type ProfileInput,
  type ProfileRecord,
} from "@/lib/profile";

const TABLE = "profiles";

export async function getProfile(userId: string) {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from(TABLE)
    .select("*")
    .eq("id", userId)
    .maybeSingle();

  if (error) throw new Error(error.message);

  return mergeProfileRecord(data as Partial<ProfileRecord> | null);
}

export async function saveProfile(userId: string, input: ProfileInput) {
  const supabase = await createClient();
  const profile = normalizeProfileInput(input);
  let existing = EMPTY_PROFILE;

  try {
    existing = await getProfile(userId);
  } catch {
    // 首次保存或表尚未就绪时回退到空资料
  }

  const payload = {
    id: userId,
    ...EMPTY_PROFILE,
    ...existing,
    ...profile,
    updated_at: new Date().toISOString(),
  };

  const { data, error } = await supabase
    .from(TABLE)
    .upsert(payload, { onConflict: "id" })
    .select("*")
    .single();

  if (error) throw new Error(error.message);

  return mergeProfileRecord(data as Partial<ProfileRecord>);
}
