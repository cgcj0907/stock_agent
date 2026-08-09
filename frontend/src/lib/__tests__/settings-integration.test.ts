import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function readSource(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("sidebar keeps only general settings entry", async () => {
  const source = await readSource("../../components/app-sidebar.tsx");

  assert.match(source, /title:\s*"通用设置".*href:\s*"\/settings"/s);
  assert.doesNotMatch(source, /title:\s*"LLM 配置".*href:\s*"\/settings\/llm"/s);
});

test("general settings page embeds llm settings client", async () => {
  const source = await readSource("../../app/(dashboard)/settings/page.tsx");

  assert.match(source, /LlmSettingsClient/);
  assert.match(source, /initialSettings=\{settings\}/);
});

test("legacy llm settings route redirects to general settings", async () => {
  const source = await readSource("../../app/(dashboard)/settings/llm/page.tsx");

  assert.match(source, /redirect\("\/settings"\)/);
});
