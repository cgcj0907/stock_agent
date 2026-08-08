import test from "node:test";
import assert from "node:assert/strict";

async function loadProfile() {
  return import(new URL("../profile.ts", import.meta.url).href);
}

test("normalizeProfileInput trims text fields and keeps valid enum values", async () => {
  const { normalizeProfileInput } = await loadProfile();

  const normalized = normalizeProfileInput({
    display_name: "  张三  ",
    avatar_url: "https://example.com/avatar.png",
    education_level: "master",
    education_major: "economics",
    education_note: "  CFA 二级，金融工程背景  ",
    career_stage: "mid_career",
    annual_income_range: "income_50_100",
    investable_assets_range: "assets_100_300",
    loss_tolerance_range: "loss_10_20",
    capital_availability: "long_term_idle",
    income_dependency_level: "medium",
    investment_goal: "long_term_compounding",
    holding_period: "long_term",
    risk_tolerance: "medium",
    investment_style: "value",
    circle_of_competence: ["consumer", "finance", "technology"],
    decision_preference: "balanced",
  });

  assert.equal(normalized.display_name, "张三");
  assert.equal(normalized.education_note, "CFA 二级，金融工程背景");
  assert.deepEqual(normalized.circle_of_competence, [
    "consumer",
    "finance",
    "technology",
  ]);
});

test("normalizeProfileInput rejects invalid enum values", async () => {
  const { normalizeProfileInput } = await loadProfile();

  assert.throws(
    () =>
      normalizeProfileInput({
        display_name: "张三",
        avatar_url: "",
        education_level: "wizard",
        education_major: "economics",
        education_note: "",
        career_stage: "mid_career",
        annual_income_range: "income_50_100",
        investable_assets_range: "assets_100_300",
        loss_tolerance_range: "loss_10_20",
        capital_availability: "long_term_idle",
        income_dependency_level: "medium",
        investment_goal: "long_term_compounding",
        holding_period: "long_term",
        risk_tolerance: "medium",
        investment_style: "value",
        circle_of_competence: ["consumer"],
        decision_preference: "balanced",
      }),
    /education_level/,
  );
});

test("normalizeProfileInput enforces circle_of_competence limit", async () => {
  const { normalizeProfileInput } = await loadProfile();

  assert.throws(
    () =>
      normalizeProfileInput({
        display_name: "张三",
        avatar_url: "",
        education_level: "master",
        education_major: "economics",
        education_note: "",
        career_stage: "mid_career",
        annual_income_range: "income_50_100",
        investable_assets_range: "assets_100_300",
        loss_tolerance_range: "loss_10_20",
        capital_availability: "long_term_idle",
        income_dependency_level: "medium",
        investment_goal: "long_term_compounding",
        holding_period: "long_term",
        risk_tolerance: "medium",
        investment_style: "value",
        circle_of_competence: [
          "consumer",
          "finance",
          "technology",
          "healthcare",
          "manufacturing",
          "energy",
        ],
        decision_preference: "balanced",
      }),
    /circle_of_competence/,
  );
});
