import { expect, test, type Page } from "@playwright/test";

async function shellStubs(page: Page) {
  await page.route("**/watchlists.json", (route) =>
    route.fulfill({ json: { items: [], alerts: [], unread: 0, webhook_configured: false } }),
  );
}

test("M2/M3 routes stay reachable from the mobile navigation", async ({ page }) => {
  await shellStubs(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/#/missing-route");
  await page.getByRole("button", { name: "เปิดเมนู" }).click();
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page.getByRole("link", { name: "Projects" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Validation Lab" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Rehearsal" })).toBeVisible();
});

test("project and rehearsal deep links reconstruct frozen workflow state", async ({ page }) => {
  await shellStubs(page);
  const now = "2026-07-17T05:00:00Z";
  await page.route("**/projects/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/evidence")) {
      return route.fulfill({
        json: {
          evidence: [
            {
              version_id: "ev1",
              item_id: "item1",
              project_id: "p1",
              label: "Pinned report",
              kind: "pdf",
              source_url: "",
              version_no: 1,
              created_at: now,
              content_hash: "a".repeat(64),
              byte_size: 120,
              media_type: "application/pdf",
              status: "ready",
              source_health: "ready",
              duplicate_of: "",
              pii_redactions: {},
              metadata: {},
            },
          ],
        },
      });
    }
    return route.fulfill({
      json: {
        project_id: "p1",
        created_at: now,
        updated_at: now,
        name: "Transit decision case",
        stage: "evidence",
        stage_index: 1,
        brief: "Evaluate the fare policy",
        population: {},
        assumptions: [],
        decision: "",
        resolution: "",
        created_by: "e2e",
        evidence_count: 1,
        runs: [],
        evidence_sets: [
          { set_id: "set1", name: "Frozen evidence", content_hash: "b".repeat(64) },
        ],
        workflow: [
          { stage: "brief", status: "complete" },
          { stage: "evidence", status: "current" },
          { stage: "population", status: "pending" },
        ],
      },
    });
  });
  await page.route("**/projects", (route) => route.fulfill({ json: { projects: [] } }));
  await page.goto("/app/#/projects/p1");
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page.getByText("Transit decision case")).toBeVisible();
  await expect(page.getByText("Pinned report")).toBeVisible();
  await expect(page.getByText("Frozen evidence")).toBeVisible();

  await page.route("**/rehearsals/session-1", (route) =>
    route.fulfill({
      json: {
        session_id: "session-1",
        created_at: now,
        updated_at: now,
        title: "Press room dry run",
        scenario: "Explain the transit policy",
        status: "paused",
        seed: 42,
        netizens: 2,
        max_turns: 3,
        reactions_per_turn: 1,
        cost_usd: 0.01,
        created_by: "e2e",
        turns: [
          {
            turn_no: 1,
            journalist: "Economics reporter",
            question: "What does it cost?",
            answer: "Within the approved budget.",
            reactions: ["Needs evidence"],
            answered: true,
          },
        ],
        decisions: [],
        scorecard: null,
        events: [],
      },
    }),
  );
  await page.route("**/rehearsals", (route) => route.fulfill({ json: { rehearsals: [] } }));
  await page.goto("/app/#/rehearsals/session-1");
  await expect(page.getByText("Press room dry run")).toBeVisible();
  await expect(page.getByText("What does it cost?")).toBeVisible();
  await expect(page.getByText("Within the approved budget.")).toBeVisible();
});

test("Validation Lab only shows a complete MIRACL result as measured", async ({ page }) => {
  await shellStubs(page);
  await page.addInitScript(() => localStorage.setItem("chimlang-lang", "en"));
  const now = "2026-07-17T05:00:00Z";
  await page.route("**/validation/overview", (route) =>
    route.fulfill({
      json: {
        datasets: [],
        reports: [
          {
            report_id: "report-complete",
            dataset_id: "miracl-th",
            created_at: now,
            kind: "miracl_retrieval",
            metrics: { recall_at_100: 0.864588, mrr_at_10: 0.455517 },
            raw_result_hash: "c".repeat(64),
            metadata: { benchmark_complete: true },
            created_by: "e2e",
            trust_status: "measured",
          },
        ],
        trust_claims: {
          miracl_measured: true,
          human_panel_measured: false,
          pilot_usability_measured: false,
        },
      },
    }),
  );
  await page.route("**/validation/resolution-inbox", (route) =>
    route.fulfill({
      json: {
        as_of: "2026-07-17",
        due: [],
        upcoming: [],
        resolved: [],
        metrics: { mean_brier: null, brier_ci95: null, ece: null, reliability: [] },
        resolution_requires_evidence: true,
      },
    }),
  );
  await page.goto("/app/#/validation");
  await expect(page.getByText("MIRACL Thai")).toBeVisible();
  await expect(page.getByText("Measured", { exact: true })).toBeVisible();
  await expect(page.getByText("measured", { exact: true })).toBeVisible();
  await expect(page.getByText("Claim blocked", { exact: true })).toHaveCount(3);
});
