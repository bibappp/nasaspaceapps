// Снимки настоящего интерфейса для лендинга (frontend/public/preview/*.jpg).
// Делаются на демо-песочнице с реальными сохранёнными данными — никаких макетов.
// Запуск: приложение должно работать (make dev), затем
//   node scripts/screenshots.cjs [http://localhost:5173]
// Нужен Playwright с Chromium (npx playwright install chromium, если его нет).
const path = require("path");
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://localhost:5173";
const OUT = path.join(__dirname, "..", "frontend", "public", "preview");

(async () => {
  const fs = require("fs");
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  for (const lang of ["ru", "kk", "en"]) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
    await ctx.addInitScript((l) => localStorage.setItem("agro.lang", l), lang);
    const page = await ctx.newPage();
    await page.goto(`${BASE}/demo`);
    await page.waitForURL("**/app", { timeout: 60000 });
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(OUT, `dashboard-${lang}.jpg`), quality: 82 });
    const href = await page.locator('table a[href^="/app/fields/"]').first().getAttribute("href");
    await page.goto(`${BASE}${href}?tab=monitoring`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);
    await page.mouse.wheel(0, 420);
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(OUT, `monitoring-${lang}.jpg`), quality: 82 });
    await page.goto(`${BASE}${href}?tab=planner`);
    await page.locator("section.panel.overflow-hidden").first().waitFor({ timeout: 60000 });
    await page.locator("section.panel.overflow-hidden").first().evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 70));
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT, `planner-${lang}.jpg`), quality: 82 });
    await ctx.close();
    console.log("ok", lang);
  }
  await browser.close();
})();
