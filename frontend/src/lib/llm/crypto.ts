import crypto from "node:crypto";

const ALGO = "aes-256-gcm";
const IV_LEN = 12;

function getKey(): Buffer {
  const secret = process.env.LLM_SETTINGS_ENCRYPTION_KEY;
  if (!secret) {
    throw new Error("缺少 LLM_SETTINGS_ENCRYPTION_KEY 环境变量");
  }
  // 任意长度口令 → 32 字节密钥
  return crypto.createHash("sha256").update(secret).digest();
}

/** AES-256-GCM 加密：返回 "iv.tag.cipher" 三段 base64 */
export function encryptSecret(plain: string): string {
  const iv = crypto.randomBytes(IV_LEN);
  const cipher = crypto.createCipheriv(ALGO, getKey(), iv);
  const enc = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return [iv, tag, enc].map((b) => b.toString("base64")).join(".");
}

/** 解密 encryptSecret 的输出 */
export function decryptSecret(blob: string): string {
  const [ivB64, tagB64, dataB64] = blob.split(".");
  if (!ivB64 || !tagB64 || !dataB64) return "";
  const decipher = crypto.createDecipheriv(
    ALGO,
    getKey(),
    Buffer.from(ivB64, "base64")
  );
  decipher.setAuthTag(Buffer.from(tagB64, "base64"));
  return Buffer.concat([
    decipher.update(Buffer.from(dataB64, "base64")),
    decipher.final(),
  ]).toString("utf8");
}

/** 脱敏展示：sk-abc…wxyz */
export function maskSecret(plain: string): string {
  if (!plain) return "";
  if (plain.length <= 8) return "••••••••";
  return `${plain.slice(0, 3)}••••••${plain.slice(-4)}`;
}
