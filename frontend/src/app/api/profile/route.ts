import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { EMPTY_PROFILE, getAvatarPublicUrl, type ProfileInput } from "@/lib/profile";
import { getProfile, saveProfile } from "@/lib/profile-store";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  try {
    const profile = await getProfile(user.id);
    return NextResponse.json({ profile });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "读取个人资料失败" },
      { status: 500 },
    );
  }
}

export async function PUT(req: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  let body: ProfileInput;
  try {
    body = (await req.json()) as ProfileInput;
  } catch {
    return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
  }

  try {
    const profile = await saveProfile(user.id, body ?? EMPTY_PROFILE);

    // 保持 Supabase Auth metadata 与资料页昵称/头像基本一致，避免侧边栏继续显示旧名字。
    const supabase = await createClient();
    await supabase.auth.updateUser({
      data: {
        display_name: profile.display_name,
        avatar_url: getAvatarPublicUrl(profile),
      },
    });

    return NextResponse.json({ profile });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "保存个人资料失败" },
      { status: 400 },
    );
  }
}
