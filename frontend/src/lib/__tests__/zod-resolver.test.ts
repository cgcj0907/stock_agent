import test from "node:test";
import assert from "node:assert/strict";
import { z } from "zod";

async function load() {
  return import(new URL("../zod-resolver.ts", import.meta.url).href);
}

test("zodResolver：合法输入返回 values 且无错误", async () => {
  const { zodResolver } = await load();
  const schema = z.object({ base_url: z.string().url(), model: z.string().min(1) });
  const r = zodResolver(schema)({
    base_url: "https://api.example.com/v1",
    model: "deepseek-chat",
  });
  assert.equal(r.values.base_url, "https://api.example.com/v1");
  assert.deepEqual(r.errors, {});
});

test("zodResolver：非法输入把 issue 映射到字段错误", async () => {
  const { zodResolver } = await load();
  const schema = z.object({ base_url: z.string().url("Base URL 格式不正确"), model: z.string().min(1, "模型必填") });
  const r = zodResolver(schema)({ base_url: "not-a-url", model: "" });
  assert.equal((r.errors as Record<string, { message: string }>).base_url.message, "Base URL 格式不正确");
  assert.equal((r.errors as Record<string, { message: string }>).model.message, "模型必填");
});
