import { NextResponse } from "next/server";

import {
  assertAvatarFile,
  AVATAR_BUCKET,
  buildAvatarPath,
} from "@/lib/avatar-storage";
import { getAvatarPublicUrl } from "@/lib/profile";
import { getProfile, saveProfile } from "@/lib/profile-store";
import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "表单数据无效" }, { status: 400 });
  }

  const file = formData.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "请先选择头像文件" }, { status: 400 });
  }

  try {
    assertAvatarFile(file);

    const supabase = await createClient();
    const current = await getProfile(user.id);
    const avatarPath = buildAvatarPath(user.id, file);
    const bytes = await file.arrayBuffer();

    const { error: uploadError } = await supabase.storage
      .from(AVATAR_BUCKET)
      .upload(avatarPath, bytes, {
        contentType: file.type,
        cacheControl: "3600",
        upsert: false,
      });

    if (uploadError) throw new Error(uploadError.message);

    if (current.avatar_path && current.avatar_path !== avatarPath) {
      await supabase.storage.from(AVATAR_BUCKET).remove([current.avatar_path]);
    }

    const profile = await saveProfile(user.id, {
      avatar_path: avatarPath,
      avatar_url: "",
    });

    await supabase.auth.updateUser({
      data: {
        avatar_url: getAvatarPublicUrl(profile),
      },
    });

    return NextResponse.json({
      profile,
      avatarUrl: getAvatarPublicUrl(profile),
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "头像上传失败" },
      { status: 400 },
    );
  }
}

export async function DELETE() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "未登录" }, { status: 401 });

  try {
    const supabase = await createClient();
    const current = await getProfile(user.id);

    if (current.avatar_path) {
      const { error } = await supabase.storage
        .from(AVATAR_BUCKET)
        .remove([current.avatar_path]);
      if (error) throw new Error(error.message);
    }

    const profile = await saveProfile(user.id, {
      avatar_path: "",
      avatar_url: "",
    });

    await supabase.auth.updateUser({
      data: {
        avatar_url: "",
      },
    });

    return NextResponse.json({ profile, avatarUrl: "" });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "移除头像失败" },
      { status: 400 },
    );
  }
}
