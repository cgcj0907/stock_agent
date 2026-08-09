export const AVATAR_BUCKET = "avatars";
export const AVATAR_MAX_BYTES = 5 * 1024 * 1024;
export const AVATAR_ALLOWED_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;

const MIME_TO_EXT: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
};

export function assertAvatarFile(file: File) {
  if (!AVATAR_ALLOWED_TYPES.includes(file.type as (typeof AVATAR_ALLOWED_TYPES)[number])) {
    throw new Error("仅支持 JPG、PNG、WebP 图片");
  }
  if (file.size <= 0) {
    throw new Error("头像文件不能为空");
  }
  if (file.size > AVATAR_MAX_BYTES) {
    throw new Error("头像文件不能超过 5MB");
  }
}

export function buildAvatarPath(userId: string, file: File) {
  const ext = MIME_TO_EXT[file.type] ?? "png";
  return `${userId}/avatar-${Date.now()}.${ext}`;
}
