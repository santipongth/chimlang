import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const emptySettings = {
  default_engine: "fabric",
  default_agents: 100,
  default_rounds: 3,
  default_domain: "general",
  default_tab: "overview",
  auth_enabled: false,
  caps: { fabric: 1000, debate: 1000 },
  llm_provider: "openrouter",
  llm_base_url: "https://openrouter.ai/api/v1",
  llm_model_crowd: "model/crowd",
  llm_model_analyst: "model/analyst",
  llm_model_embedding: "",
  llm_embedding_dimension: 1536,
  llm_prices: {},
  run_budget_usd_cap: 5,
  monthly_budget_usd_cap: 50,
  llm: {
    providers: [],
    key_present: true,
    key_masked: "configured",
    key_source: "db",
    master_key_present: true,
    active_base_url: "https://openrouter.ai/api/v1",
    active_model_crowd: "model/crowd",
    active_model_analyst: "model/analyst",
    active_model_embedding: "",
    embedding_dimension: 1536,
    env_model_crowd: "",
    env_model_analyst: "",
    env_model_embedding: "",
    yaml_prices: {},
  },
  budget: {
    run_cap_effective: 5,
    monthly_cap_effective: 50,
    spent_this_month: 0,
    reserved_this_month: 0,
    available_this_month: 50,
    env_run_cap: 5,
    env_monthly_cap: 50,
  },
  news: {
    tavily_present: false,
    tavily_masked: "",
    tavily_source: "none",
  },
};

async function fulfill(route: Route, json: unknown) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(json) });
}

async function stubApi(page: Page) {
  await page.route("**/*", async (route) => {
    const request = route.request();
    if (!["fetch", "xhr"].includes(request.resourceType())) return route.continue();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/engines.json")) return fulfill(route, { engines: [{ key: "fabric", label_th: "Fabric", label_en: "Fabric", desc_th: "แบบจำลองเชิงกล", desc_en: "Mechanistic model", uses_llm: false, max_agents: 1000 }] });
    if (path.endsWith("/settings.json")) return fulfill(route, emptySettings);
    if (path.endsWith("/personas/packs.json")) return fulfill(route, { packs: [] });
    if (path.endsWith("/personas/pool.json")) return fulfill(route, { source: "census", segments: [], limits: { min_segments: 2, max_segments: 12 } });
    if (path.endsWith("/simruns.json")) return fulfill(route, { runs: [] });
    if (path.endsWith("/run-metrics.json")) return fulfill(route, { queued: 0, running: 0, failed: 0, completed: 0, canceled: 0, sources_by_status: {}, news_by_status: {}, recent: [], runs_24h: [], spent_this_month: 0 });
    if (path.endsWith("/graph/summary.json")) return fulfill(route, { nodes: [], edges: [], hubs: [], kinds: [], note: "" });
    if (path.endsWith("/insights.json")) return fulfill(route, { total_runs: 0, exports: 0, runs_per_day: [], predictions_by_domain: [] });
    if (path.endsWith("/observability.json")) return fulfill(route, { window_hours: 24, providers: [], failure_taxonomy: [], queue: { queued: 0, running: 0, errors: 0, avg_latency_seconds: 0 }, pii_policy: "fail-closed" });
    if (path.endsWith("/experiments")) return fulfill(route, { experiments: [] });
    if (path.endsWith("/gallery.json")) return fulfill(route, { items: [] });
    if (path.endsWith("/health/deep")) return fulfill(route, { status: "ok", components: {} });
    if (path.endsWith("/product-policy.json")) return fulfill(route, { version: "test", billing_enabled: false, repository_public: false, semantic_memory_enabled: false, items: [], note: "" });
    return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "accessibility test stub" }) });
  });
}

const routes = [
  "/",
  "/new",
  "/history",
  "/insights",
  "/experiments",
  "/gallery",
  "/settings",
];

test("all application routes pass automated WCAG 2.2 AA checks in English", async ({ page }) => {
  await stubApi(page);
  await page.addInitScript(() => localStorage.setItem("chimlang-lang", "en"));
  for (const route of routes) {
    await page.goto("/app/#" + route);
    await expect(page.locator("main")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(results.violations, route + " accessibility violations").toEqual([]);
    const text = (await page.locator("main").innerText()).replaceAll("ชิมลาง", "");
    expect(text, route + " contains untranslated Thai UI").not.toMatch(/[ก-๙]/);
  }
});

test("language, skip-link, focus, reflow and target controls are operable", async ({ page }) => {
  await stubApi(page);
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/app/#/settings");
  await expect(page.locator("html")).toHaveAttribute("lang", "th");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "ข้ามไปเนื้อหาหลัก" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await page.getByRole("button", { name: "เปิดเมนู" }).click();
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("main")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  // เกณฑ์เดิม (≤ 1px) — เพิ่ม diagnostics เพื่อให้ log CI ระบุ element ตัวการเมื่อ fail
  // (เคย fail บน ubuntu-latest ที่ font rendering ต่างจากเครื่อง dev โดย log ไม่บอกอะไรเลย)
  const overflowingElements = overflow > 1
    ? await page.evaluate(() => {
        const limit = document.documentElement.clientWidth;
        return Array.from(document.querySelectorAll<HTMLElement>("body *"))
          .filter((el) => el.getBoundingClientRect().right > limit + 1)
          .slice(0, 8)
          .map((el) => {
            const box = el.getBoundingClientRect();
            const text = (el.textContent || "").trim().slice(0, 60);
            return `${el.tagName}.${String(el.className).slice(0, 60)} right=${Math.round(box.right)} text="${text}"`;
          });
      })
    : [];
  expect(overflow, `horizontal overflow ${overflow}px; culprits: ${overflowingElements.join(" | ")}`).toBeLessThanOrEqual(1);
  const smallControls = await page.locator("main button:visible, main a:visible, main input:visible, main select:visible").evaluateAll((items) =>
    items.filter((item) => {
      const box = item.getBoundingClientRect();
      return box.width < 24 || box.height < 24;
    }).map((item) => {
      const box = item.getBoundingClientRect();
      return item.tagName + ":" + (item.textContent || item.getAttribute("aria-label") || "") + ":" + box.width + "x" + box.height;
    }),
  );
  expect(smallControls).toEqual([]);
});
