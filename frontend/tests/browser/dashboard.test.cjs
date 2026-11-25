const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const path = require("node:path");
const readline = require("node:readline");
const { setTimeout: delay } = require("node:timers/promises");
const { after, before, test } = require("node:test");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "../../..");
const python = process.env.MGTS_TEST_PYTHON ||
  path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
let server;
let browser;
let origin;

before(async () => {
  const timeout = AbortSignal.timeout(20_000);
  server = spawn(python, ["-B", "-m", "frontend.tests.browser.fixture_app"], {
    cwd: root, stdio: ["ignore", "pipe", "inherit"],
  });
  const stdout = readline.createInterface({ input: server.stdout });
  const [port] = await Promise.race([
    once(stdout, "line", { signal: timeout }),
    once(server, "exit", { signal: timeout }).then(([code]) => {
      throw new Error("Тестовый FastAPI завершился с кодом " + code);
    }),
  ]);
  assert.match(port, /^\d+$/);
  origin = "http://127.0.0.1:" + port;
  while (!timeout.aborted) {
    if (await fetch(origin + "/api/overview").then((r) => r.ok).catch(() => false)) break;
    await delay(100, undefined, { signal: timeout });
  }
  timeout.throwIfAborted();
  browser = await chromium.launch({ executablePath: process.env.MGTS_TEST_CHROMIUM || undefined });
});

after(async () => {
  try {
    await browser?.close();
  } finally {
    if (server && server.exitCode === null && server.signalCode === null) {
      const exited = once(server, "exit");
      server.kill();
      await exited;
    }
  }
});

async function withPage(context, options, scenario) {
  const page = await browser.newPage({ reducedMotion: "reduce", ...options });
  context.after(() => page.close());
  const exceptions = [];
  page.on("pageerror", (error) => exceptions.push(error.message));
  await scenario(page);
  assert.deepEqual(exceptions, []);
}

async function activeElementId(page, id) {
  await page.waitForFunction((target) => document.activeElement.id === target, id);
}

async function checkAccessibility(page) {
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  const violations = await page.evaluate(async () => {
    const audit = await axe.run({
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    });
    return audit.violations.map(({ id, nodes }) => ({
      id, targets: nodes.map((node) => node.target.join(" ")),
    }));
  });
  assert.deepEqual(violations, []);
}

test("Клавиатура, профиль и переход к исходным оценкам", async (context) => {
  await withPage(context, { viewport: { width: 1440, height: 900 } }, async (page) => {
    let overviewRequests = 0;
    page.on("request", (request) => {
      if (request.url() === origin + "/api/overview") overviewRequests++;
    });
    await page.goto(origin);
    await page.getByRole("heading", { name: "Обзор программы" }).waitFor();
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.textContent), "К содержанию");
    await page.keyboard.press("Enter");
    await activeElementId(page, "main");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await activeElementId(page, "intern-directory");
    assert.equal(overviewRequests, 1);

    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await page.getByRole("heading", { name: "Стажёр INT-01", exact: true }).waitFor();
    await activeElementId(page, "main");
    await page.getByRole("heading", { name: "Последний отзыв наставника" }).waitFor();
    assert.equal(await page.locator(".intern-comments article").count(), 6);
    await page.getByText("Тестовое заключение по стажёру.", { exact: true }).waitFor();

    const tableLink = page.getByRole("link", { name: "Значения графика в таблице" });
    await tableLink.focus();
    await page.keyboard.press("Enter");
    await activeElementId(page, "monthly");
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute("aria-label")), "Помесячная таблица оценок");
    assert.equal(overviewRequests, 2);
    await checkAccessibility(page);

    await page.goBack();
    await page.goBack();
    await page.getByRole("heading", { name: "Обзор программы" }).waitFor();
    await activeElementId(page, "intern-directory");
  });
});

for (const width of [320, 390, 768, 1440]) {
  test("Читаемый обзор и загрузка диаграмм при прокрутке, " + width + " px", async (context) => {
    await withPage(context, { viewport: { width, height: 820 } }, async (page) => {
      const scriptRequests = [];
      page.on("request", (request) => {
        if (request.url().endsWith("/assets-vendor/plotly.js")) scriptRequests.push(request);
      });
      await page.goto(origin);
      await page.getByRole("heading", { name: "Обзор программы" }).waitFor();
      await page.getByText("Тестовое заключение по программе.", { exact: true }).waitFor();
      assert.equal(await page.locator(".secondary-chart .main-svg").count(), 0);
      assert.equal(await page.locator(".directory-row").count(), 5);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.getByRole("table", { name: "Все показатели по месяцам" }).waitFor();
      assert.match(await page.locator("#chart-summary").innerText(), /месяц 1 — 4,6 \/ 10.*месяц 6 — 9,2 \/ 10/);
      const firstPlot = page.locator(".secondary-chart .chart").first();
      await firstPlot.scrollIntoViewIfNeeded();
      await firstPlot.locator(".main-svg").first().waitFor();
      assert.equal(scriptRequests.length, 1);
      if (width === 320) await checkAccessibility(page);
    });
  });
}

test("Таблица остаётся доступной при сбое загрузки библиотеки графиков", async (context) => {
  await withPage(context, { viewport: { width: 1280, height: 900 } }, async (page) => {
    await page.route("**/assets-vendor/plotly.js", (route) => route.abort());
    await page.goto(origin + "/interns/INT-02#monthly");
    await activeElementId(page, "monthly");
    await page.getByRole("table", { name: "Все показатели по месяцам" }).waitFor();
    await page.locator(".chart-panel").scrollIntoViewIfNeeded();
    await page.locator(".chart-panel").getByText(/Диаграмма недоступна/).waitFor();
    await page.getByText("Тестовое заключение по стажёру.", { exact: true }).waitFor();
  });
});

test("Все типы диаграмм сохраняют анимацию после отложенной загрузки", async (context) => {
  await withPage(context, { viewport: { width: 1440, height: 900 }, reducedMotion: "no-preference" }, async (page) => {
    await page.addInitScript(() => {
      window.animatedCharts = new WeakMap();
      const animate = Element.prototype.animate;
      Element.prototype.animate = function (frames, options) {
        const chart = this.closest(".chart");
        const trace = chart?.data?.[0];
        if (trace && this instanceof SVGElement) {
          window.animatedCharts.set(chart, trace.mode === "markers" ? "points" : trace.type);
        }
        return animate.call(this, frames, options);
      };
    });
    async function checkCharts(types) {
      const charts = page.locator(".chart");
      for (const [index, type] of types.entries()) {
        await charts.nth(index).scrollIntoViewIfNeeded();
        await page.waitForFunction(([position, kind]) =>
          window.animatedCharts.get(document.querySelectorAll(".chart")[position]) === kind, [index, type]);
      }
    }

    await page.goto(origin);
    await page.getByRole("heading", { name: "Обзор программы" }).waitFor();
    await checkCharts(["scatter", "scatter", "scatter", "bar", "pie"]);
    await page.goto(origin + "/interns/INT-02");
    await page.getByRole("heading", { name: "Стажёр INT-02", exact: true }).waitFor();
    await checkCharts(["scatter", "scatterpolar", "points"]);
  });
});
