import { redirect } from "next/navigation";

import { ProfileSettingsClient } from "./profile-settings-client";
import { mergeProfileRecord } from "@/lib/profile";
import { getProfile } from "@/lib/profile-store";
import { getCurrentUser } from "@/lib/supabase/auth";

export default async function ProfileSettingsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  let profile = mergeProfileRecord({
    id: user.id,
    display_name:
      (user.user_metadata?.display_name as string | undefined) ??
      user.email?.split("@")[0] ??
      "",
    avatar_url: (user.user_metadata?.avatar_url as string | undefined) ?? "",
  });

  try {
    profile = mergeProfileRecord({
      id: user.id,
      ...profile,
      ...(await getProfile(user.id)),
    });
  } catch {
    // profiles 表或新字段尚未落库时回退到 Auth metadata，页面仍可正常展示。
  }

  return <ProfileSettingsClient initialProfile={profile} email={user.email ?? ""} />;
}
