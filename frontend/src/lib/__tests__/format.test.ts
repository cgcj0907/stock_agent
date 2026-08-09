import test from "node:test";
import assert from "node:assert/strict";

async function load() {
  return import(new URL("../format.ts", import.meta.url).href);
}

test("formatNumber：千分位 + 最多 2 位小数", async () => {
  const { formatNumber } = await load();
  assert.equal(formatNumber(48.76), "48.76");
  assert.equal(formatNumber(1234567.5), "1,234,567.5");
  assert.equal(formatNumber(null), "—");
  assert.equal(formatNumber(Number.NaN), "—");
});

test("formatPrice：金额单位与位数", async () => {
  const { formatPrice } = await load();
  assert.equal(formatPrice(48.76), "48.76");
  assert.equal(formatPrice(12345), "1.2 万");
  assert.equal(formatPrice(123456789), "1.23 亿");
  assert.equal(formatPrice(undefined), "—");
});

test("formatBigNumber：亿/万/千分位", async () => {
  const { formatBigNumber } = await load();
  assert.equal(formatBigNumber(123456789), "1.23 亿");
  assert.equal(formatBigNumber(45678), "4.6 万");
  assert.equal(formatBigNumber(999), "999");
  assert.equal(formatBigNumber(null), "—");
});

test("formatPct / formatPct1：小数比例 → 百分比", async () => {
  const { formatPct, formatPct1 } = await load();
  assert.equal(formatPct(0.123), "12%");
  assert.equal(formatPct1(0.1234), "12.3%");
  assert.equal(formatPct(null), "—");
});

test("formatSignedPct：带符号百分比", async () => {
  const { formatSignedPct } = await load();
  assert.equal(formatSignedPct(0.123), "+12.3%");
  assert.equal(formatSignedPct(-0.05), "-5.0%");
  assert.equal(formatSignedPct(undefined), "—");
});
