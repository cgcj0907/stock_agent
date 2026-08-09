import test from "node:test";
import assert from "node:assert/strict";

async function load() {
  return import(new URL("../auth/safe-next.ts", import.meta.url).href);
}

test("safeNext 缺省回首页", async () => {
  const { safeNext } = await load();
  assert.equal(safeNext(null), "/");
  assert.equal(safeNext(undefined), "/");
  assert.equal(safeNext(""), "/");
});

test("safeNext 放行站内相对路径", async () => {
  const { safeNext } = await load();
  assert.equal(safeNext("/"), "/");
  assert.equal(safeNext("/conversations/abc"), "/conversations/abc");
  assert.equal(safeNext("/agents?tab=fav"), "/agents?tab=fav");
});

test("safeNext 拦截外部与协议相对地址", async () => {
  const { safeNext } = await load();
  assert.equal(safeNext("https://evil.com"), "/");
  assert.equal(safeNext("//evil.com"), "/");
  assert.equal(safeNext("javascript:alert(1)"), "/");
  assert.equal(safeNext("not-a-path"), "/");
});
