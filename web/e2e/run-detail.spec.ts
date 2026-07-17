import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const run = {
  run_id: "e2e-run",
  created_at: "2026-07-16T09:00:00Z",
  engine: "debate",
  subject: "E2E policy debate",
  domain: "policy",
  agents: 4,
  rounds: 2,
  status: "complete",
  seed: 101,
  config: { views: ["overview", "debate", "canvas", "evidence"], live_news: true },
  payload: {
    synthesis: {
      summary: "Most segments support the policy, but rural respondents remain cautious.",
      confidence: 0.76,
      distribution: [{ bucket: "support", pct: 62 }, { bucket: "oppose", pct: 24 }],
      key_drivers: ["Lower cost", "Clear communication"],
      risks: ["Uneven trust"],
    },
    metrics: {
      posts_failed: 0,
      per_round_avg_stance: [0.15, 0.42],
      tipping_points: [{ round: 1, delta: 0.27 }],
    },
    protocol: {
      per_round_disagreement: [
        { round: 0, oppose: 1, neutral: 1, support: 2, dispersion: 0.32 },
        { round: 1, oppose: 1, neutral: 0, support: 3, dispersion: 0.58 },
      ],
      contention_graph: { nodes: [], edges: [] },
      failure_taxonomy: {},
    },
    sources: [{ status: "ready", label: "briefing", chunks: 2 }],
    news: { enabled: true, items: [{ status: "ready", provider: "rss", title: "signal", fetched_at: "2026-07-16T08:50:00Z" }] },
    evidence_matches: [],
    cost_usd: 0.015,
  },
  error: null,
  posts: [
    { round_no: 0, agent_idx: 1, segment: "urban", content: "supports rollout", stance: 0.6, sentiment: 0.4, failed: false },
    { round_no: 0, agent_idx: 2, segment: "rural", content: "has doubts", stance: -0.1, sentiment: -0.2, failed: false },
    { round_no: 1, agent_idx: 3, segment: "urban", content: "strong support", stance: 0.9, sentiment: 0.5, failed: false },
    { round_no: 1, agent_idx: 4, segment: "rural", content: "strong concern", stance: -0.65, sentiment: -0.4, failed: false },
  ],
  result_kind: "simulation_finding",
  findings: [{ finding_id: 1, created_at: "2026-07-16T09:01:00Z", summary: "Support is positive but contested.", metrics: {}, provenance: {}, model_version: "test" }],
  predictions: [],
  synthesis_revisions: [],
  parent_run_id: null,
  events: [],
  trust_scorecard: { score: 82, band: "usable", checks: [{ id: "contract", label: "Contract", status: "pass", detail: "finding present" }] },
};

async function installRoutes(page: Page) {
  await page.route("**/watchlists.json", async (route) => {
    await route.fulfill({ json: { items: [], alerts: [], unread: 0, webhook_configured: false } });
  });
  await page.route("**/runs/e2e-run.json", async (route) => {
    await route.fulfill({ json: run });
  });
}

test("opens run detail by URL and renders nonblank visualization canvas", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/app/#/runs/e2e-run");

  await expect(page.getByRole("heading", { name: "E2E policy debate" })).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Most segments support the policy, but rural respondents remain cautious.",
    }),
  ).toBeVisible();
  await expect(page.getByTestId("stance-timeline-chart")).toBeVisible();
  await expect(page.getByTestId("contention-graph")).toBeVisible();

  const canvas = page.locator('[data-testid="stance-timeline-chart"] canvas').first();
  await expect(canvas).toBeVisible();
  await expect
    .poll(async () => canvas.evaluate((node: HTMLCanvasElement) => {
      const context = node.getContext("2d");
      if (!context || node.width === 0 || node.height === 0) return false;
      const pixels = context.getImageData(0, 0, node.width, node.height).data;
      for (let i = 3; i < pixels.length; i += 4) {
        if (pixels[i] !== 0) return true;
      }
      return false;
    }))
    .toBe(true);

  await page.getByRole("button", { name: /urban/ }).click();
  await expect(page.getByText("Posts: urban")).toBeVisible();
  await expect(page.getByText(/strong support/)).toBeVisible();
});

test("keeps visualization fallbacks usable on mobile", async ({ page }) => {
  await installRoutes(page);
  await page.goto("/app/#/runs/e2e-run");

  await expect(page.getByText(/Stance timeline/)).toBeVisible();
  await page.getByRole("button", { name: /Evidence|Evidence trail|เส้นทาง|หลักฐาน/ }).click();
  await expect(page.getByTestId("evidence-lineage-chart")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence lineage" })).toBeVisible();
  await expect(page.getByText(/ตารางข้อมูล: Evidence lineage/)).toBeVisible();
});

test("virtualizes a 1,000-post Debate feed", async ({ page }) => {
  const largeRun = {
    ...run,
    run_id: "e2e-large-run",
    agents: 1000,
    rounds: 1,
    posts: Array.from({ length: 1000 }, (_, index) => ({
      round_no: 0,
      agent_idx: index,
      segment: `กลุ่ม ${index}`,
      content: `โพสต์ทดสอบลำดับ ${index}`,
      stance: (index % 20) / 10 - 1,
      sentiment: 0,
      failed: false,
      move_id: `move-${index}`,
      move_type: "claim",
    })),
  };
  await page.route("**/watchlists.json", async (route) => {
    await route.fulfill({ json: { items: [], alerts: [], unread: 0, webhook_configured: false } });
  });
  await page.route("**/runs/e2e-large-run.json", async (route) => {
    await route.fulfill({ json: largeRun });
  });
  await page.goto("/app/#/runs/e2e-large-run");
  await page.getByRole("button", { name: /การถกเถียง|Debate/ }).click();

  const list = page.getByTestId("virtual-debate-list");
  await expect(list).toBeVisible();
  await expect.poll(() => page.getByTestId("debate-post-row").count()).toBeLessThan(30);
  await list.evaluate((node) => {
    node.scrollTop = 132 * 500;
    node.dispatchEvent(new Event("scroll", { bubbles: true }));
  });
  await expect(page.getByText("โพสต์ทดสอบลำดับ 500", { exact: true })).toBeVisible();
  await expect.poll(() => page.getByTestId("debate-post-row").count()).toBeLessThan(30);
});
