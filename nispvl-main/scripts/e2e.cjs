// Сквозная проверка в браузере: регистрация -> поле из GeoJSON -> планировщик с засухой 2021 -> свои веса ->
// PDF/XLSX -> выход и вход -> чужое поле недоступно. Нужен запущенный `make dev` и Playwright с Chromium.
//   node scripts/e2e.cjs [http://localhost:5173]
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");
const B = process.argv[2] || "http://localhost:5173";
const S = fs.mkdtempSync(path.join(os.tmpdir(), "agro-e2e-")) + path.sep;
// контур демо-поля в Костанайской области — его данные лежат в data/demo, расчёт не требует сети
const demo = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "data", "demo", "fields", "kostanay", "field.json"), "utf8"));
fs.writeFileSync(S + "kostanay.geojson", JSON.stringify({ type: "Feature", properties: {}, geometry: demo.geometry }));
fs.mkdirSync(S + "shots", { recursive: true });
const ok = (c, m) => { if (!c) { console.log("FAIL", m); process.exitCode = 1; } else console.log("ok  ", m); };
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => m.type() === "error" && !m.text().includes("401") && errs.push(m.text().slice(0, 200)));
  const email = `e2e${Date.now()}@example.org`;
  await page.goto(B + "/register");
  await page.getByLabel(/Имя/).fill("Тест");
  await page.getByLabel(/Хозяйство/).fill("ТОО Тест");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel(/^Пароль/).fill("password123");
  await page.getByLabel("Повторите пароль").fill("password123");
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await page.waitForURL("**/app/fields/new");
  ok(true, "register -> new field");
  await page.locator('input[type=file]').setInputFiles(S + "kostanay.geojson");
  await page.getByLabel("Название").fill("Поле у Костаная");
  await page.locator("select").first().selectOption("kostanay");
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Сохранить" }).click();
  await page.waitForURL(/\/app\/fields\/\d+$/);
  const fieldUrl = page.url();
  ok(true, "field saved " + fieldUrl);
  await page.waitForTimeout(4000);
  await page.goto(fieldUrl + "?tab=planner");
  await page.getByRole("button", { name: "Рассчитать и сохранить" }).waitFor();
  await page.locator("select").filter({ hasText: "автоматически" }).selectOption("2021");
  await page.getByRole("button", { name: "Рассчитать и сохранить" }).click();
  await page.getByText("Рекомендуемый вариант").first().waitFor({ timeout: 60000 });
  ok(true, "analysis computed with stress year 2021");
  const rec1 = await page.locator("h2.text-xl").first().textContent();
  // крайние веса: только доход, затем только риск
  const sliders = page.locator('input[type=range]');
  for (const [i, v] of [[0, 0], [1, 0], [2, 100], [3, 0]]) await sliders.nth(i).fill(String(v));
  const recIncome = await page.locator("h2.text-xl").first().textContent();
  for (const [i, v] of [[0, 0], [1, 0], [2, 0], [3, 100]]) await sliders.nth(i).fill(String(v));
  const recRisk = await page.locator("h2.text-xl").first().textContent();
  ok(await page.getByText("Рейтинг пересчитан").isVisible(), "re-rank banner shown");
  console.log("     recommended:", rec1, "| income-only:", recIncome, "| risk-only:", recRisk);
  await page.getByRole("button", { name: "Сохранить с этими весами" }).click();
  await page.waitForTimeout(3000);
  ok(!(await page.getByText("Рейтинг пересчитан").isVisible()), "saved with custom weights");
  await page.goto(fieldUrl + "?tab=reports");
  await page.getByText("Сохранённые анализы").waitFor();
  await page.locator("table tbody tr").nth(1).waitFor({ timeout: 15000 });
  const rows = await page.locator("table tbody tr").count();
  ok(rows === 2, "two saved analyses listed: " + rows);
  for (const [label, ext] of [["Скачать PDF", ".pdf"], ["Скачать Excel", ".xlsx"]]) {
    await page.locator("select").first().selectOption("en");
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), page.getByRole("button", { name: label }).click()]);
    const p = S + "e2e" + ext; await dl.saveAs(p);
    ok(dl.suggestedFilename().endsWith(ext), "download " + dl.suggestedFilename());
  }
  const [dl2] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), page.locator("table tbody tr").first().getByRole("button", { name: "PDF" }).click()]);
  await dl2.saveAs(S + "e2e-saved.pdf"); ok(true, "saved-analysis pdf " + dl2.suggestedFilename());
  // выход и вход: данные сохранились
  await page.goto(B + "/app");
  await page.getByRole("button", { name: "Выйти" }).click();
  await page.waitForURL(B + "/");
  await page.goto(B + "/app"); await page.waitForURL("**/login");
  ok(true, "logged out, /app redirects to login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Пароль").fill("password123");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await page.waitForURL("**/app");
  await page.getByText("Поле у Костаная").first().waitFor();
  ok(true, "login again: field persisted");
  // английский интерфейс
  await page.getByRole("button", { name: "EN" }).click();
  await page.goto(fieldUrl + "?tab=planner");
  await page.getByText("Recommended option").first().waitFor({ timeout: 30000 });
  await page.screenshot({ path: S + "shots/en-planner.png", fullPage: false });
  await page.getByRole("button", { name: "KZ" }).click();
  await page.goto(fieldUrl + "?tab=risk"); await page.waitForTimeout(3000);
  await page.screenshot({ path: S + "shots/kk-risk.png", fullPage: true });
  // изоляция: чужое поле
  const other = await page.request.get(B + "/api/fields/1");
  ok(other.status() === 404, "other user's field -> " + other.status());
  console.log(errs.slice(0, 10).join("\n"));
  await browser.close();
})();
