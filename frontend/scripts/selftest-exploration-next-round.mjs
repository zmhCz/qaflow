import assert from "node:assert/strict";
import { buildAINextRoundReadiness } from "../src/views/app-automation/exploration/readiness.mjs";

const cases = [
  {
    name: "no ai analysis keeps the card hidden",
    input: { hasAnalysis: false, targetCount: 3 },
    expected: { visible: false, ready: false, blocker: "" },
  },
  {
    name: "ai analysis without targets blocks next round",
    input: { hasAnalysis: true, targetCount: 0 },
    expected: { visible: true, ready: false, blocker: "缺少目标" },
  },
  {
    name: "failed acceptance blocks next round before issue review",
    input: {
      hasAnalysis: true,
      targetCount: 3,
      acceptanceFailedCount: 2,
      pendingIssueCount: 1,
    },
    expected: { visible: true, ready: false, blocker: "验收未过" },
  },
  {
    name: "pending issues block next round after acceptance passes",
    input: {
      hasAnalysis: true,
      targetCount: 3,
      acceptanceFailedCount: 0,
      pendingIssueCount: 1,
    },
    expected: { visible: true, ready: false, blocker: "待复核" },
  },
  {
    name: "analysis with targets and no blockers is ready",
    input: {
      hasAnalysis: true,
      targetCount: 3,
      acceptanceFailedCount: 0,
      pendingIssueCount: 0,
    },
    expected: { visible: true, ready: true, blocker: "" },
  },
];

for (const item of cases) {
  const actual = buildAINextRoundReadiness(item.input);
  assert.equal(actual.visible, item.expected.visible, `${item.name}: visible`);
  assert.equal(actual.ready, item.expected.ready, `${item.name}: ready`);
  assert.equal(actual.blocker, item.expected.blocker, `${item.name}: blocker`);
  assert.equal(typeof actual.title, "string", `${item.name}: title`);
  assert.equal(
    typeof actual.description,
    "string",
    `${item.name}: description`,
  );
}

console.log(
  `AI exploration next-round readiness self-test passed: ${cases.length} cases`,
);
