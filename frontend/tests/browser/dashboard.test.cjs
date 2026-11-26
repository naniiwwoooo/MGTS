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
  page.setDefaultTimeout(8000);
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
    assert.equal(await page.evaluate(() => document.activeElement.id), "coverage-month");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await page.getByRole("heading", { name: "Стажёр СТ-001", exact: true }).waitFor();
    await activeElementId(page, "main");
    await page.getByRole("heading", { name: "Последний отзыв наставника" }).waitFor();
    assert.equal(await page.locator(".intern-comments article").count(), 12);
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
      const table = page.getByRole("table", { name: "Все показатели по месяцам" });
      await table.waitFor();
      assert.equal(await table.locator("tbody tr").first().locator("td").last().locator(".monthly-count").textContent(), "Ответов: 5");
      assert.match(await page.locator("#chart-summary").innerText(), /месяц 1 — 3,6 \/ 5.*месяц 6 — 5 \/ 5/);
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
    await page.goto(origin + "/interns/" + encodeURIComponent("СТ-002") + "#monthly");
    await activeElementId(page, "monthly");
    await page.getByRole("table", { name: "Все показатели по месяцам" }).waitFor();
    await page.locator(".chart-panel .chart").scrollIntoViewIfNeeded();
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
      const charts = page.locator(".chart:visible");
      for (const [index, type] of types.entries()) {
        const chart = charts.nth(index);
        await chart.evaluate((element) => element.scrollIntoView({ block: "center" }));
        const handle = await chart.elementHandle();
        try {
          await page.waitForFunction(([element, kind]) => window.animatedCharts.get(element) === kind,
            [handle, type]);
        } catch (error) {
          const state = await chart.evaluate((element) => ({
            expected: element.parentElement.querySelector("h2, h3").textContent,
            actual: element.data?.[0]?.type, animated: window.animatedCharts.get(element),
          }));
          throw new Error("Состояние графика: " + JSON.stringify(state), { cause: error });
        }
        await handle.dispose();
      }
    }

    await page.goto(origin);
    await page.getByRole("heading", { name: "Обзор программы" }).waitFor();
    await checkCharts(["bar", "scatter", "scatter", "scatter", "scatter", "scatter"]);
    await page.goto(origin + "/interns/" + encodeURIComponent("СТ-002"));
    await page.getByRole("heading", { name: "Стажёр СТ-002", exact: true }).waitFor();
    await checkCharts(["scatter", "scatter", "scatter", "scatter", "scatter"]);
  });
});


for (const width of [390, 1440]) {
  test("Ассистент отвечает из открытого контекста, " + width + " px", async (context) => {
    await withPage(context, { viewport: { width, height: 820 } }, async (page) => {
      await page.goto(origin);
      await page.getByRole("button", { name: "Открыть чат" }).click();
      const dialog = page.getByRole("dialog", { name: "Помощник по данным" });
      await dialog.getByText("Данные: обзор программы").waitFor();
      const inputBounds = await dialog.getByRole("textbox", { name: "Ваш вопрос" }).boundingBox();
      assert(inputBounds.y >= 0 && inputBounds.y + inputBounds.height <= 820);
      await checkAccessibility(page);
      await dialog.getByRole("button", { name: "Как изменилось профессиональное развитие?" }).click();
      await dialog.getByText(/4,2 из 5.*5 из 5/).waitFor();
      await dialog.getByRole("link", { name: "Профессиональное развитие · Стажеры" }).click();
      await activeElementId(page, "monthly-development-0");

      await page.getByRole("link", { name: /^СТ-002/ }).last().click();
      await page.getByRole("button", { name: "Открыть чат" }).click();
      await dialog.getByText("Данные: стажёр СТ-002").waitFor();
      assert.equal(await dialog.getByText(/4,2 из 5/).count(), 0);
      await dialog.getByRole("button", { name: "Покажи последний отзыв наставника" }).click();
      await dialog.getByRole("link", { name: "Комментарий в профиле" }).click();
      await activeElementId(page, "fresh-feedback");
      await page.getByRole("button", { name: "Открыть чат" }).click();
      const input = dialog.getByRole("textbox", { name: "Ваш вопрос" });
      await input.fill("Какая погода?");
      await input.press("Enter");
      await dialog.getByText(/Отвечаю только по данным/).waitFor();
      await page.keyboard.press("Escape");
      await dialog.waitFor({ state: "hidden" });
      assert.equal(await page.evaluate(() => document.activeElement.textContent), "Открыть чат");
    });
  });
}

test("Запоздалый ответ обзора не появляется в чате стажёра", async (context) => {
  await withPage(context, { viewport: { width: 1440, height: 900 } }, async (page) => {
    const release = Promise.withResolvers();
    const started = Promise.withResolvers();
    await page.route("**/api/assistant/overview", async (route) => {
      started.resolve();
      await release.promise;
      await route.fulfill({ json: { status: "answered", text: "Запоздалый ответ обзора" } }).catch(() => {});
    });
    await page.goto(origin);
    await page.getByRole("button", { name: "Открыть чат" }).click();
    try {
      await page.getByRole("button", { name: "Как изменилось профессиональное развитие?" }).click();
      await started.promise;
      await page.getByRole("navigation", { name: "Разделы" }).getByRole("link", { name: "СТ-002" }).click();
      await page.getByRole("heading", { name: "Стажёр СТ-002", exact: true }).waitFor();
    } finally {
      release.resolve();
    }
    await page.getByRole("button", { name: "Открыть чат" }).click();
    await page.getByText("Данные: стажёр СТ-002").last().waitFor();
    assert.equal(await page.getByRole("dialog").getByText("Запоздалый ответ обзора").count(), 0);
  });
});

test("История показывает все контрольные месяцы и пять анкет каждого типа", async (context) => {
  await withPage(context, { viewport: { width: 1440, height: 900 } }, async (page) => {
    await page.goto(origin);
    await page.getByRole("heading", { name: "Обзор программы" }).waitFor();
    const period = page.getByLabel("Статус анкет за месяц");
    for (const month of ["1", "4", "6"]) {
      await period.selectOption(month);
      assert.equal(await page.locator('.directory-row .submission[data-submitted="true"]').count(), 10);
    }
    await page.getByRole("button", { name: "Обновить данные" }).click();
    await page.getByText(/исторические анкеты Excel · актуально/).waitFor();
  });
});

test("Дашборд перечитывает данные после смены версии без перезапуска страницы", async (context) => {
  await withPage(context, { viewport: { width: 1440, height: 900 } }, async (page) => {
    await page.goto(origin);
    await page.getByRole("heading", { name: "Обзор программы" }).waitFor();
    const original = await page.request.get(origin + "/api/overview").then(response => response.json());
    const next = { ...original, data_version: "updated-test" };
    next.metrics[0].change.latest.value = 3.2;
    next.metrics[0].value = 3.2;
    next.sync = { state: "connected" };
    await page.route("**/api/data-status", route => route.fulfill({
      json: { data_version: next.data_version, sync: next.sync },
    }));
    await page.route("**/api/overview", route => route.fulfill({ json: next }));
    await page.route("**/api/analysis/overview?*", route => route.fulfill({ json: { status: "unavailable" } }));
    await page.evaluate(() => { window.dashboardPageSentinel = true; });
    await page.getByRole("button", { name: "Обновить данные" }).click();
    await page.getByText("История Excel и ответы Google Forms").waitFor();
    await page.locator(".metric-value").first().getByText("3,2", { exact: false }).waitFor();
    assert.equal(await page.evaluate(() => window.dashboardPageSentinel), true);
  });
});
