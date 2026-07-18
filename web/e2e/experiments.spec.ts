import { expect, test } from "@playwright/test";

const detail = {
  workspace: {
    experiment_id: "exp-e2e",
    name: "เปรียบเทียบแคมเปญ",
    kind: "comparison",
    config: {},
    created_at: "2026-07-16T10:00:00Z",
    run_count: 2,
  },
  analysis: {
    runs: [
      { run_id: "run-a", engine: "fabric", subject: "A", status: "complete", seed: 41, variant: {}, value: 0.42, cost_usd: 0 },
      { run_id: "run-b", engine: "fabric", subject: "B", status: "complete", seed: 42, variant: {}, value: 0.61, cost_usd: 0 },
    ],
    completed: 2,
    failed: 0,
    total_cost_usd: 0,
    sensitivity: [],
    ranked_sensitivity: [],
    public_votes_used: false,
    note: "snapshot comparison",
  },
};

test("opens the experiment workspace by URL and compares arbitrary runs", async ({ page }) => {
  await page.route("**/experiments**", async (route) => {
    const request = route.request();
    if (request.method() === "POST" && request.url().endsWith("/experiments/compare")) {
      await route.fulfill({ json: detail });
      return;
    }
    if (request.url().endsWith("/experiments")) {
      await route.fulfill({ json: { experiments: [] } });
      return;
    }
    await route.fulfill({ json: detail });
  });

  await page.goto("/app/#/experiments");
  await expect(page.getByRole("heading", { name: "เปรียบเทียบและการทดลอง" })).toBeVisible();
  await page.getByPlaceholder("ชื่อเวิร์กสเปซ").fill("เปรียบเทียบแคมเปญ");
  await page.getByPlaceholder("Run IDs คั่นด้วย comma หรือขึ้นบรรทัดใหม่").fill("run-a, run-b");
  await page.getByRole("button", { name: "สร้างการเปรียบเทียบ" }).click();

  await expect(page.getByRole("heading", { name: "เปรียบเทียบแคมเปญ" })).toBeVisible();
  await expect(page.getByText("run-a", { exact: true })).toBeVisible();
  await expect(page.getByText("run-b", { exact: true })).toBeVisible();
  await expect(page.getByText("ระบบนำคะแนนสาธารณะเข้า engine: ไม่")).toBeVisible();
});
