import { expect, test, type Page } from "@playwright/test";

async function watchlistStub(page: Page) {
  await page.route("**/watchlists.json", (route) =>
    route.fulfill({ json: { items: [], alerts: [], unread: 0, webhook_configured: false } }),
  );
}

test("mobile drawer is keyboard reachable and invalid routes are bilingual", async ({ page }, testInfo) => {
  await watchlistStub(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/#/missing-route");

  await expect(page.getByRole("heading", { name: "ไม่พบหน้าที่ต้องการ" })).toBeVisible();
  await page.getByRole("button", { name: "เปิดเมนู" }).click();
  const close = page.getByRole("button", { name: "ปิดเมนู" }).last();
  await expect(close).toBeFocused();
  await page.screenshot({
    path: `../.tmp/p9-mobile-drawer-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "EN" }).click();
  await page.getByRole("button", { name: "Close navigation" }).last().click();
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeFocused();
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();

  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "History" }).click();
  await expect(page).toHaveURL(/#\/history$/);
});

test("gallery share token opens directly through the typed route", async ({ page }) => {
  await watchlistStub(page);
  await page.route("**/gallery.json", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/gallery/share-e2e.json", (route) =>
    route.fulfill({
      json: {
        share_token: "share-e2e",
        created_at: "2026-07-17T00:00:00Z",
        subject: "ผล snapshot ที่แชร์โดยตรง",
        agents: 20,
        watermark: { note: "AI simulation — not a real poll" },
        votes: { agree: 2, disagree: 1 },
        payload: {
          brief: { lines: [{ kind: "finding", text: "ผลจำลองที่เก็บไว้" }], fragility_index: 20, confidence_label: "medium" },
          scenarios: [],
        },
      },
    }),
  );

  await page.goto("/app/#/gallery/share-e2e");
  await expect(page.getByRole("heading", { name: "ผล snapshot ที่แชร์โดยตรง" })).toBeVisible();
  await expect(page.getByText("ผลจำลองที่เก็บไว้")).toBeVisible();
});

test("202 accepted navigates immediately to running detail and supports cancel", async ({ page }, testInfo) => {
  await watchlistStub(page);
  let status: "queued" | "canceled" = "queued";
  let idempotencyKey = "";
  await page.route("**/engines.json", (route) =>
    route.fulfill({
      json: {
        engines: [
          {
            key: "fabric",
            label_th: "Fabric",
            label_en: "Fabric",
            desc_th: "แบบจำลองเชิงกล",
            desc_en: "Mechanistic model",
            uses_llm: false,
            max_agents: 1000,
          },
        ],
      },
    }),
  );
  await page.route("**/settings.json", (route) =>
    route.fulfill({
      json: {
        default_engine: "fabric",
        default_agents: 100,
        default_rounds: 3,
        default_domain: "การเงิน/ตลาดทุน",
      },
    }),
  );
  await page.route("**/personas/packs.json", (route) => route.fulfill({ json: { packs: [] } }));
  await page.route("**/personas/pool.json**", (route) =>
    route.fulfill({ json: { source: "census", segments: [], limits: { min_segments: 2, max_segments: 12 } } }),
  );
  await page.route("**/runs/readiness", (route) =>
    route.fulfill({
      json: {
        can_run: true,
        checks: [{ id: "governance", label: "Governance", status: "pass", detail: "ready" }],
        cost: { estimated_usd: 0 },
      },
    }),
  );
  await page.route("**/runs/async", async (route) => {
    idempotencyKey = route.request().headers()["idempotency-key"] ?? "";
    await route.fulfill({
      status: 202,
      json: {
        run_id: "e2e-accepted",
        job_id: "job-e2e",
        status: "queued",
        reused: false,
        status_url: "/runs/e2e-accepted.json",
        events_url: "/runs/e2e-accepted/events/stream",
        manifest_url: "/runs/e2e-accepted/manifest",
        snapshot_url: "/runs/e2e-accepted/snapshot",
      },
    });
  });
  await page.route("**/runs/e2e-accepted.json", (route) =>
    route.fulfill({
      json: {
        run_id: "e2e-accepted",
        created_at: "2026-07-17T00:00:00Z",
        engine: "fabric",
        subject: "ทดสอบเปิดหน้ารันทันที",
        domain: "ทั่วไป",
        agents: 100,
        rounds: 20,
        status,
        seed: 42,
        config: {},
        payload: null,
        error: status === "canceled" ? "ยกเลิกโดยผู้ใช้" : null,
        posts: [],
        events: [{ created_at: "2026-07-17T00:00:00Z", event_type: status, actor: "system", message: status, payload: {} }],
        progress: status === "queued" ? 0 : 10,
        progress_message: status,
        manifest: { schema_version: 1, complete: false, reproducibility: "incomplete" },
      },
    }),
  );
  await page.route("**/runs/e2e-accepted/events/stream**", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: "id: 1\ndata: {\id\:1,\event_type\:\queued\,\stage\:\queue\,\message\:\queued\}\n\n" }),
  );
  await page.route("**/runs/e2e-accepted/cancel", async (route) => {
    status = "canceled";
    await route.fulfill({ json: { ok: true, status: "canceled", transitioned: true } });
  });

  await page.goto("/app/#/new");
  const next = page.getByRole("button", { name: /ถัดไป/ });
  await expect(next).toBeDisabled();
  await page.getByPlaceholder("จะเกิดอะไรถ้า...").fill("ทดสอบเปิดหน้ารันทันที");
  await next.click();
  await next.click();
  await next.click();
  await expect(page.getByText("Ready to run")).toBeVisible();
  await page.getByRole("button", { name: /รันจำลอง/ }).click();

  await expect(page).toHaveURL(/#\/runs\/e2e-accepted$/);
  await expect(page.getByRole("heading", { name: "ทดสอบเปิดหน้ารันทันที" })).toBeVisible();
  await expect(page.getByText("ลำดับขั้นการรัน")).toBeVisible();
  expect(idempotencyKey.length).toBeGreaterThan(8);
  await page.screenshot({
    path: `../.tmp/p9-running-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "ยกเลิกรัน" }).click();
  await expect(page.getByText("ยกเลิกแล้ว")).toBeVisible();
});
