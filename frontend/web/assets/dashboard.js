import { renderAssistant } from "./assistant.js";

const main = document.querySelector("main");
const directoryNav = document.querySelector("#intern-navigation");
const mobileIntern = document.querySelector("#mobile-intern");
const template = document.querySelector("#page-template");
const plurals = new Intl.PluralRules("ru-RU");
const format = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });
const dateFormat = new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" });
let routeController;
let plotlyLoading;
let activePath;
let navIds = [];
let historyExpanded = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function link(text, href, className) {
  const node = element("a", text, className);
  node.href = href;
  node.dataset.route = "";
  return node;
}

function internPath(id) {
  return "/interns/" + encodeURIComponent(id);
}

function score(value, scale) {
  if (value === null) return "Нет оценки";
  return format.format(value) + (scale ? " / " + scale : "");
}

const palette = {
  blue: "#0075ed", violet: "#8050dc", green: "#159166",
  amber: "#dd850e", rose: "#db475c", neutral: "#8790a0",
};

function rating(value, scale) {
  if (value === null || !scale) return null;
  if (value <= 2) return { tone: "rose", label: "Низкая оценка" };
  if (value < 4) return { tone: "amber", label: "Средняя оценка" };
  return { tone: "green", label: "Высокая оценка" };
}

function month(value) {
  return "Месяц " + value;
}

async function request(url, signal, method = "GET") {
  const response = await fetch(url, { signal, method, cache: "no-store" });
  if (!response.ok) {
    const { detail } = await response.json().catch(() => ({}));
    const error = new Error(typeof detail === "string" ? detail : "Не удалось загрузить данные.");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function markNavigation(id) {
  document.querySelectorAll(".nav-link").forEach((node) => {
    if (node.pathname === (id ? internPath(id) : "/")) node.setAttribute("aria-current", "page");
    else node.removeAttribute("aria-current");
  });
  mobileIntern.value = navIds.includes(id) ? id : "";
  document.querySelector(".mobile-navigation .overview-link").hidden = !id;
}

function renderNavigation(interns, recentIds, id) {
  navIds = interns.map((intern) => intern.id);
  const recent = recentIds.filter((internId) => navIds.includes(internId));
  const older = navIds.filter((internId) => !recent.includes(internId));
  directoryNav.replaceChildren(element("p", "Стажёры", "sidebar-label"));
  mobileIntern.replaceChildren(new Option("Выберите профиль", ""));
  const profileLink = (internId) => link(internId, internPath(internId), "nav-link");
  directoryNav.append(...recent.map(profileLink));
  if (older.length) {
    const toggle = element("button", undefined, "nav-history-toggle");
    toggle.type = "button";
    const history = element("div");
    history.id = "intern-navigation-history";
    history.append(...older.map(profileLink));
    toggle.setAttribute("aria-controls", history.id);
    historyExpanded ||= older.includes(id);
    function showHistory() {
      history.hidden = !historyExpanded;
      toggle.setAttribute("aria-expanded", String(historyExpanded));
      toggle.textContent = historyExpanded ? "Свернуть историю" : "Все стажёры (" + navIds.length + ")";
    }
    toggle.addEventListener("click", () => {
      historyExpanded = !historyExpanded;
      showHistory();
    });
    showHistory();
    directoryNav.append(toggle, history);
  }
  for (const internId of [...recent, ...older]) {
    mobileIntern.add(new Option(internId, internId));
  }
  mobileIntern.disabled = navIds.length === 0;
  markNavigation(id);
}

function responseLabel(count) {
  const noun = { one: "ответ", few: "ответа", many: "ответов" }[plurals.select(count)] || "ответов";
  return count + " " + noun;
}

function changeLabel(change) {
  if (!change || change.first.month === change.latest.month) return "Нет данных для сравнения";
  const { first, latest } = change;
  return format.format(first.value) + " → " + format.format(latest.value) +
    " · мес. " + first.month + "–" + latest.month;
}

function renderMetrics(page, metrics, isProfile) {
  const grid = page.querySelector(".metric-grid");
  grid.classList.toggle("profile-metrics", isProfile);
  for (const metric of metrics) {
    const card = element("article", undefined, "metric");
    const latest = metric.change?.latest;
    const measured = metric.value;
    const participantAverage = metric.participants != null;
    const value = element("div", measured === null ? "—" : format.format(measured), "metric-value");
    if (measured !== null) value.append(element("small", " / " + metric.scale));
    const participants = { one: "стажёр", few: "стажёра", many: "стажёров" };
    const subtitle = participantAverage && metric.participants
      ? "По последней оценке каждого · " + metric.participants + " " + participants[plurals.select(metric.participants)]
      : latest ? metric.source + " · мес. " + latest.month + " · " + responseLabel(latest.responses)
      : metric.source + " · нет оценки";
    const quality = rating(measured, metric.scale);
    if (!participantAverage && metric.change && metric.change.first.month !== latest.month) {
      const delta = Number((latest.value - metric.change.first.value).toFixed(2));
      const badge = element("small", (delta > 0 ? "+" : "") + format.format(delta), "metric-delta");
      badge.dataset.direction = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
      badge.title = "Изменение в баллах к первой доступной оценке";
      value.append(badge);
    }
    if (quality) card.dataset.tone = quality.tone;
    card.append(element("h2", metric.label), value, element("p", subtitle));
    card.append(element("p", (participantAverage && metric.change?.first.month !== latest?.month ? "По месяцам: " : "") +
      changeLabel(metric.change), "metric-change"));
    grid.append(card);
  }
}

function submission(submitted) {
  const mark = element("span", submitted ? "Сдана" : "Нет ответа", "submission");
  mark.dataset.submitted = String(submitted);
  return mark;
}

function renderDirectory(page, interns) {
  page.querySelector(".directory").hidden = false;
  page.querySelector(".directory-jump").hidden = false;
  const list = page.querySelector(".directory-list");
  const select = page.querySelector("#coverage-month");
  for (let month = 1; month <= 6; month++) select.add(new Option("Месяц " + month, month));
  select.value = String(Math.max(1, ...interns.flatMap(item => item.coverage
    .filter(check => check.intern_submitted || check.mentor_submitted).map(check => check.month))));
  function update() {
    const period = Number(select.value);
    const heading = element("div", undefined, "directory-header");
    heading.setAttribute("aria-hidden", "true");
    for (const title of ["Стажер", "Анкета стажера", "Анкета наставника", "Статус"]) {
      heading.append(element("span", title));
    }
    list.replaceChildren(heading);
    for (const intern of interns) {
      const checks = intern.coverage.find(item => item.month === period);
      const alerts = intern.signals.filter(item => item.months.includes(period));
      const row = link(undefined, internPath(intern.id), "directory-row");
      const identity = element("div");
      identity.append(element("strong", intern.id), element("small", intern.department));
      const own = element("div");
      own.append(element("small", "Анкета стажера", "row-label"), submission(checks.intern_submitted));
      const mentor = element("div");
      mentor.append(element("small", "Анкета наставника", "row-label"), submission(checks.mentor_submitted));
      if (checks.submitted_mentors.length) mentor.append(element("small", checks.submitted_mentors.join(", ")));
      if (checks.pending_mentors.length) mentor.append(element("small", "Нет ответа: " + checks.pending_mentors.join(", ")));
      const status = element("div", undefined, "row-progress");
      const urgent = alerts.some(item => item.level === "critical");
      const text = urgent ? "Критичный сигнал" : alerts.length ? "Зона внимания" :
        checks.intern_submitted && checks.mentor_submitted && !checks.pending_mentors.length ? "Сигналов нет" : "Данные неполные";
      const badge = element("span", text, "signal-badge");
      badge.dataset.level = urgent ? "critical" : alerts.length ? "attention" : "clear";
      status.append(badge);
      if (alerts.length) status.append(element("small", alerts[0].label));
      const arrow = element("span", "›");
      arrow.setAttribute("aria-hidden", "true");
      row.append(identity, own, mentor, status, arrow);
      list.append(row);
    }
  }
  select.addEventListener("change", update);
  update();
}

function renderMonitor(page, profile) {
  const monitor = page.querySelector(".profile-monitor");
  monitor.hidden = false;
  const table = valuesTable("Сдача анкет по месяцам", ["Месяц", "Анкета стажера", "Анкета наставника"],
    profile.coverage.map(item => [item.month, submission(item.intern_submitted), submission(item.mentor_submitted)]));
  page.querySelector(".profile-coverage").append(table);
  const list = page.querySelector(".profile-signals");
  for (const signal of profile.signals) {
    const row = element("li");
    const badge = element("span", signal.level === "critical" ? "Критичный сигнал" : "Зона внимания", "signal-badge");
    badge.dataset.level = signal.level;
    const source = element("a", signal.source === "feedback" ? "Комментарии" : "Оценки", "chart-table-link");
    source.href = "#" + signal.source;
    row.append(badge, element("strong", signal.label), element("p", signal.detail + " Месяцы: " + signal.months.join(", ") + "."), source);
    list.append(row);
  }
  if (!profile.signals.length) list.append(element("li", "Сигналов по правилам мониторинга нет."));
}

function commentCard(comment) {
  const article = element("article");
  const attribution = month(comment.month) + " · " + comment.author;
  article.append(element("p", attribution, "comment-meta"), element("strong", comment.question), element("p", comment.text));
  return article;
}

function renderComments(page, profile) {
  page.querySelector(".feedback").hidden = false;
  const fresh = page.querySelector(".fresh-feedback");
  const newestMonth = profile.comments[0]?.month;
  if (newestMonth !== undefined) {
    fresh.hidden = false;
    fresh.append(...profile.comments.filter((comment) => comment.month === newestMonth).map(commentCard));
  }
  const interns = page.querySelector(".intern-comments");
  const mentors = page.querySelector(".mentor-comments");
  const earlier = profile.comments.filter((comment) => comment.month !== newestMonth);
  interns.append(...(profile.intern_comments.length ? profile.intern_comments.map(commentCard) : [
    element("p", "Комментариев стажёра пока нет."),
  ]));
  mentors.append(...(earlier.length ? earlier.map(commentCard) : [
    element("p", newestMonth === undefined ? "Отзывов пока нет." : "Более ранних отзывов нет."),
  ]));
}

function loadPlotly() {
  if (!plotlyLoading) {
    plotlyLoading = new Promise((resolve, reject) => {
      const script = element("script");
      script.src = "/assets-vendor/plotly.js";
      script.onload = () => resolve(window.Plotly);
      script.onerror = () => {
        script.remove();
        reject(new Error("Не удалось загрузить библиотеку графиков."));
      };
      document.head.append(script);
    }).catch((error) => {
      plotlyLoading = undefined;
      throw error;
    });
  }
  return plotlyLoading;
}

function revealChart(graph, trace, signal, motion) {
  const timing = { duration: 580, easing: "cubic-bezier(.22,.75,.24,1)", fill: "backwards" };
  const effects = {
    bars: [".barlayer .point path", [
      { opacity: .3, transform: "scaleY(.02)" }, { opacity: 1, transform: "scaleY(1)" },
    ]],
    ring: [".pielayer", [
      { opacity: 0, clipPath: "circle(14% at 50% 50%)" },
      { opacity: 1, clipPath: "circle(75% at 50% 50%)" },
    ]],
    radar: [".polarlayer .scatterlayer", [
      { opacity: 0, clipPath: "circle(10% at 50% 50%)" },
      { opacity: 1, clipPath: "circle(75% at 50% 50%)" },
    ]],
    points: [".scatterlayer .points .point", [{ opacity: 0 }, { opacity: 1 }]],
    line: [".scatterlayer", [
      { opacity: .55, clipPath: "inset(-10px 100% -10px -10px)" },
      { opacity: 1, clipPath: "inset(-10px -10px -10px -10px)" },
    ]],
  };
  const type = { bar: "bars", pie: "ring", scatterpolar: "radar" }[trace.type]
    || (trace.mode === "markers" ? "points" : "line");
  const animations = [];

  const observer = new IntersectionObserver(([entry]) => {
    if (signal.aborted || !entry.isIntersecting) return;
    observer.disconnect();
    graph.classList.remove("chart-awaiting");
    if (motion.matches) return;
    const [selector, frames] = effects[type];
    const shapes = graph.querySelectorAll(selector);
    if (!shapes.length) {
      animations.push(graph.animate([{ opacity: 0, translate: "0 6px" }, { opacity: 1, translate: "0 0" }], timing));
      return;
    }
    shapes.forEach((shape, index) => {
      animations.push(shape.animate(frames, {
        ...timing,
        delay: type === "bars" || type === "points" ? Math.min(index * 35, 210) : 0,
      }));
    });
  }, { threshold: .18 });

  observer.observe(graph);
  signal.addEventListener("abort", () => {
    observer.disconnect();
    animations.forEach((animation) => animation.cancel());
  }, { once: true });
}

function drawChart(graph, traces, layout, signal) {
  if (!traces.length) {
    graph.removeAttribute("aria-hidden");
    graph.append(element("p", "Недостаточно данных для диаграммы."));
    return;
  }

  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const observe = "IntersectionObserver" in window;
  function render() {
    const animate = !motion.matches && observe && typeof graph.animate === "function";
    if (animate) graph.classList.add("chart-awaiting");
    loadPlotly().then(async (plotly) => {
      if (signal.aborted) return;
      signal.addEventListener("abort", () => plotly.purge(graph), { once: true });
      await plotly.newPlot(graph, traces, {
        height: 262, margin: { t: 14, r: 18, b: 48, l: 42 },
        font: { family: "system-ui, sans-serif", color: "#555a64", size: 12 },
        paper_bgcolor: "transparent", plot_bgcolor: "transparent", separators: ", ",
        showlegend: false, ...layout,
      }, { responsive: true, displayModeBar: false, scrollZoom: false });
      if (animate && !signal.aborted) revealChart(graph, traces[0], signal, motion);
    }).catch(() => {
      if (signal.aborted) return;
      graph.classList.remove("chart-awaiting");
      graph.removeAttribute("aria-hidden");
      graph.replaceChildren(element("p", "Диаграмма недоступна. Значения приведены в таблице."));
    });
  }

  if (!observe) {
    render();
    return;
  }
  const observer = new IntersectionObserver(([entry]) => {
    if (signal.aborted || !entry.isIntersecting) return;
    observer.disconnect();
    render();
  }, { rootMargin: "200px 0px" });
  observer.observe(graph);
  signal.addEventListener("abort", () => observer.disconnect(), { once: true });
}

function describeSeries(chart) {
  return chart.series.map((series) => {
    const observations = series.points.filter(({ value }) => value !== null);
    if (!observations.length) return series.label + ": нет оценок.";
    const first = observations[0];
    const last = observations.at(-1);
    const value = (point) => score(point.value, chart.scale?.[1]) + (chart.unit ? " " + chart.unit : "");
    const previous = first !== last ? "месяц " + first.month + " — " + value(first) + "; " : "";
    return series.label + ": " + previous + "месяц " + last.month + " — " + value(last) + ".";
  }).join(" ");
}

function trendFigure(chart) {
  const series = chart.series.filter((item) => item.points.some(({ value }) => value !== null));
  const [minimum, maximum] = chart.scale;
  return {
    traces: series.map((item, index) => ({
      type: "scatter", mode: "lines+markers", name: item.label,
      x: item.points.map(({ month }) => month), y: item.points.map(({ value }) => value),
      line: { color: [palette.blue, palette.violet][index], width: 3, dash: index ? "dash" : "solid" },
      marker: { size: 8, symbol: index ? "diamond" : "circle" },
      connectgaps: false,
    })),
    layout: {
      xaxis: { dtick: 1, title: { text: "Месяц" }, showgrid: false },
      yaxis: { range: [minimum - .2, maximum + .2], dtick: maximum === 10 ? 2 : 1, gridcolor: "#e9edf3" },
      showlegend: series.length > 1,
      legend: { orientation: "h", x: 0, y: 1.03, yanchor: "bottom" },
    },
  };
}

function renderMainChart(page, data, signal) {
  const own = data.charts.find(({ id }) => id === "clarity");
  const mentor = data.charts.find(({ id }) => id === "expectations");
  const chart = {
    ...own, series: [
      { ...own.series[0], label: "Стажеры · понятность задач" },
      { ...mentor.series[0], label: "Наставники · понимание задач" },
    ],
  };
  page.querySelector("#chart-summary").textContent = describeSeries(chart);
  const { traces, layout } = trendFigure(chart);
  drawChart(page.querySelector(".chart-panel .chart"), traces, layout, signal);
}

function renderMonthly(page, charts) {
  const months = charts[0].series[0].points.map((point) => String(point.month));
  const rows = charts.flatMap((chart) => chart.series.map((series) => {
    const source = " · " + series.label;
    const unit = chart.scale ? chart.scale.join("–") : chart.unit;
    return [chart.label + source + (unit ? " (" + unit + ")" : ""),
      ...series.points.map(({ value, responses }) => {
        const result = document.createDocumentFragment();
        const count = element("small", undefined, "monthly-count");
        count.append(element("span", "Ответов: ", "visually-hidden"), String(responses));
        result.append(value === null ? "—" : format.format(value), count);
        return result;
      })];
  }));
  const table = valuesTable("Все показатели по месяцам", ["Показатель / месяц", ...months], rows);
  table.classList.add("monthly-table");
  charts.flatMap((chart) => chart.series.map((_, index) => chart.id + "-" + index)).forEach((key, index) => {
    const row = table.tBodies[0].rows[index];
    row.id = "monthly-" + key;
    row.tabIndex = -1;
  });
  page.querySelector(".monthly .table-scroll").append(table);
}

function valuesTable(label, headers, rows) {
  const table = element("table");
  table.setAttribute("aria-label", label);
  const header = table.createTHead().insertRow();
  for (const title of headers) {
    const cell = element("th", title);
    cell.scope = "col";
    header.append(cell);
  }
  const body = table.createTBody();
  for (const [label, ...values] of rows) {
    const row = body.insertRow();
    const cell = element("th", label);
    cell.scope = "row";
    row.append(cell);
    for (const value of values) row.insertCell().append(value instanceof Node ? value : String(value));
  }
  return table;
}

function renderAdditionalCharts(page, data, isProfile, signal) {
  page.querySelector("#chart-section-heading").textContent = isProfile ? "Профиль и оценки наставника" : "Динамика и наставничество";
  const grid = page.querySelector(".chart-grid");
  const axes = { fixedrange: true, gridcolor: "#eaedf1", zeroline: false };

  function panel(title, caption, traces, layout) {
    const card = element("section", undefined, "panel secondary-chart");
    const graph = element("div", undefined, "chart");
    graph.setAttribute("aria-hidden", "true");
    card.append(element("h3", title), element("p", caption, "chart-caption"), graph);
    const tableLink = element("a", "Помесячные значения", "chart-table-link");
    tableLink.href = "#monthly";
    card.append(tableLink);
    grid.append(card);
    drawChart(graph, traces, layout, signal);
  }

  const selected = isProfile ? ["development", "quality", "autonomy", "deadlines"] : ["satisfaction", "development", "quality", "autonomy"];
  for (const key of selected) {
    const chart = data.charts.find(({ id }) => id === key);
    const { traces, layout } = trendFigure(chart);
    panel(chart.label, describeSeries(chart), traces, layout);
  }
  if (!isProfile) {
    const rail = page.querySelector(".rail-chart");
    rail.hidden = false;
    rail.querySelector(".chart-caption").textContent = "Число стажеров с ответом в каждом из двух опросов.";
    const traces = [
      { type:"bar", name:"Стажеры", marker:{ color: palette.blue },
        x:[1,2,3,4,5,6], y:[1,2,3,4,5,6].map(month => data.interns.filter(item => item.coverage[month - 1].intern_submitted).length) },
      { type:"bar", name:"Наставники", marker:{ color: palette.violet },
        x:[1,2,3,4,5,6], y:[1,2,3,4,5,6].map(month => data.interns.filter(item => item.coverage[month - 1].mentor_submitted).length) },
    ];
    drawChart(rail.querySelector(".chart"), traces, {
      height: 185, margin: { t: 30, r: 10, b: 28, l: 30 }, barmode: "group",
      showlegend: true, legend: { orientation: "h", x: 0, y: 1.16 },
      xaxis: { ...axes, dtick: 1, showgrid: false }, yaxis: { ...axes, dtick: 1, range: [0, data.intern_count + 1] },
    }, signal);
  }
}

function revealAnalysis(output, text, signal, animate) {
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const readable = element("span", text);
  if (!animate || motion.matches) {
    output.append(readable);
    return;
  }

  const wrapper = element("div", undefined, "analysis-reveal");
  const animated = element("span", undefined, "analysis-typing");
  animated.setAttribute("aria-hidden", "true");
  readable.classList.add("analysis-reserve");
  wrapper.append(readable, animated);
  const skip = element("button", "Показать весь вывод", "analysis-skip");
  skip.type = "button";
  output.append(wrapper, skip);

  const characters = Intl.Segmenter
    ? Array.from(new Intl.Segmenter("ru", { granularity: "grapheme" }).segment(text), ({ segment }) => segment)
    : Array.from(text);
  const letters = characters.map((character) => element("span", character, "analysis-letter"));
  animated.append(...letters);

  let next = 0;
  let previousFrame = -Infinity;
  function finish() {
    animated.remove();
    readable.classList.remove("analysis-reserve");
    skip.remove();
  }
  skip.addEventListener("click", () => {
    finish();
    output.tabIndex = -1;
    output.focus({ preventScroll: true });
  });
  function step(now) {
    if (signal.aborted || !animated.isConnected) return;
    if (motion.matches || document.hidden) {
      finish();
      return;
    }
    if (now - previousFrame >= 13) {
      letters[next++].classList.add("is-visible");
      previousFrame = now;
    }
    if (next < letters.length) requestAnimationFrame(step);
    else setTimeout(finish, 130);
  }
  requestAnimationFrame(step);
}

function renderEvidence(page, data) {
  const list = page.querySelector(".analysis-evidence ul");
  for (const metric of data.metrics) {
    if (!metric.change) continue;
    const { first, latest } = metric.change;
    const line = element("li");
    const previous = first.month === latest.month ? "" :
      format.format(first.value) + " · мес. " + first.month + ", " + responseLabel(first.responses) + " → ";
    line.append(element("strong", metric.label), element("small",
      metric.source + " · " + previous + score(latest.value, metric.scale) +
      " · мес. " + latest.month + ", " + responseLabel(latest.responses)));
    list.append(line);
  }
  if (!list.children.length) list.append(element("li", "В опросах пока нет оценок для вывода."));
}

function renderAnalysis(page, id, data, signal) {
  const { first_month: startMonth, last_month: endMonth } = data;
  const query = "?version=" + encodeURIComponent(data.data_version);
  const endpoint = id ? "/api" + internPath(id) + "/analysis" : "/api/analysis/overview";
  const button = page.querySelector(".analysis-action");
  const output = page.querySelector(".analysis-output");
  page.querySelector("#analysis-heading").textContent = id ? "ИИ-вывод по стажёру" : "ИИ-вывод по программе";
  page.querySelector(".analysis-period").textContent =
    startMonth === endMonth ? month(startMonth) : "Месяцы " + startMonth + "–" + endMonth;

  let freshlyRequested = false;
  let reloadData = false;
  const messages = {
    available: "Анализ ещё не сформирован.",
    unavailable: "ИИ-анализ доступен после подключения модели.",
    running: "Формируем вывод по данным опросов…",
    error: "Не удалось получить вывод. Попробуйте ещё раз.",
  };

  function show(result) {
    if (signal.aborted) return;
    const { status } = result;
    output.textContent = status === "ready" ? "" : result.error_message || messages[status];
    output.classList.toggle("analysis-running", status === "running");
    if (status === "ready") revealAnalysis(output, result.text, signal, freshlyRequested);
    button.hidden = !["ready", "error", "available"].includes(status);
    button.disabled = status === "running";
    button.textContent = reloadData ? "Обновить данные" : {
      ready: "Обновить вывод", running: "Готовим вывод…", error: "Повторить",
    }[status] || "Сформировать вывод";
    if (status === "error" && result.text) {
      output.append(element("p", result.text));
    }
    if (result.generated_at) {
      const time = element("small", "Сформирован " + dateFormat.format(new Date(result.generated_at)), "analysis-time");
      output.append(time);
    }
    if (status === "running") {
      const timer = setTimeout(() => {
        signal.removeEventListener("abort", stop);
        refresh();
      }, 900);
      const stop = () => clearTimeout(timer);
      signal.addEventListener("abort", stop, { once: true });
    }
  }

  async function refresh(method = "GET", reuse = false) {
    if (method === "POST") {
      freshlyRequested = true;
      button.disabled = true;
      output.textContent = messages.running;
      output.classList.add("analysis-running");
    }
    try {
      const result = await request(endpoint + query + (reuse ? "&refresh=false" : ""), signal, method);
      if (reuse && result.status === "ready") freshlyRequested = false;
      show(result);
    } catch (error) {
      if (signal.aborted) return;
      reloadData = error.status === 409;
      show({ status: "error", error_message: reloadData ? error.message : null });
    }
  }

  button.addEventListener("click", () => reloadData ? renderRoute(true) : refresh("POST"));
  refresh("POST", true);
}

function watchUpdates(page, data, signal) {
  const status = page.querySelector(".source-status");
  const refresh = page.querySelector(".data-refresh");
  function describe(sync) {
    status.textContent = {
      history: "Источник: исторические анкеты Excel",
      connected: sync.sources?.length === 1
        ? (sync.sources[0] === "interns"
          ? "Ответы стажёров из Google Forms и Excel · Оценки наставников из Excel"
          : "Ответы стажёров из Excel · Оценки наставников из Google Forms и Excel")
        : "Опросы стажёров и наставников из Google Forms и Excel",
      partial: "Часть опросов Google Forms временно недоступна. Для неё показаны последние доступные данные.",
      error: "Google Forms временно недоступен. Показаны последние доступные данные.",
    }[sync.state];
    if (sync.detail) status.textContent += " " + sync.detail;
  }
  describe(data.sync);
  let checking = false;
  async function check(manual = false) {
    if (checking || signal.aborted || (!manual && document.hidden)) return;
    checking = true;
    refresh.disabled = true;
    try {
      const update = await request("/api/data-status", signal);
      if (signal.aborted) return;
      if (update.data_version !== data.data_version) {
        if (!manual && page.querySelector("dialog").open) status.textContent = "Поступили новые ответы. Обновите страницу после завершения диалога.";
        else renderRoute(manual);
      } else {
        describe(update.sync);
        if (manual && update.sync.state !== "error" && !update.sync.detail) status.textContent += " · актуально";
      }
    } catch {
      if (!signal.aborted) status.textContent = "Не удалось проверить обновления. Можно повторить.";
    } finally {
      checking = false;
      refresh.disabled = false;
    }
  }
  refresh.addEventListener("click", () => check(true));
  const timer = setInterval(check, 15_000);
  signal.addEventListener("abort", () => clearInterval(timer), { once: true });
}

async function renderRoute(focus = false) {
  routeController?.abort();
  activePath = location.pathname;
  routeController = new AbortController();
  const { signal } = routeController;
  let id;
  let overviewRequest;
  try {
    id = location.pathname.startsWith("/interns/") ? decodeURIComponent(location.pathname.slice(9)) : null;
    markNavigation(id);
    const loading = element("p", "Загружаем данные…", "loading");
    loading.setAttribute("role", "status");
    main.replaceChildren(loading);
    overviewRequest = request("/api/overview", signal);
    const [overview, profile] = await Promise.all([
      overviewRequest, id ? request("/api" + internPath(id), signal) : Promise.resolve(null),
    ]);
    if (signal.aborted) return;
    if (profile && overview.data_version !== profile.data_version) {
      throw new Error("Опросы обновились во время загрузки. Попробуйте ещё раз.");
    }
    renderNavigation(overview.interns, overview.recent_intern_ids, id);
    const page = template.content.cloneNode(true).firstElementChild;
    const title = id ? "Стажёр " + id : "Обзор программы";
    document.title = title + " · МГТС";
    page.querySelector("h1").textContent = title;
    page.querySelector(".page-meta").textContent = profile ? profile.department + " · шесть контрольных точек"
      : "Месяцы " + overview.first_month + "–" + overview.last_month + " · Стажёры: " + overview.intern_count +
        " (" + responseLabel(overview.intern_responses) + ") · Наставники: " +
        overview.mentor_count + " (" + responseLabel(overview.mentor_responses) + ")";
    const data = profile || overview;
    page.classList.toggle("profile", Boolean(profile));
    renderMetrics(page, data.metrics, Boolean(profile));
    renderMonthly(page, data.charts);
    if (profile) {
      renderMonitor(page, profile);
      renderComments(page, profile);
    }
    else renderDirectory(page, overview.interns);
    main.replaceChildren(page);
    renderMainChart(page, data, signal);
    renderAdditionalCharts(page, data, Boolean(profile), signal);
    renderEvidence(page, data);
    renderAnalysis(page, id, data, signal);
    renderAssistant(page, id, data.data_version, signal);
    watchUpdates(page, data, signal);
    if (location.hash) focusSection(location.hash);
    else if (focus) main.focus({ preventScroll: true });
  } catch (error) {
    if (signal.aborted) return;
    const panel = element("section", undefined, "error");
    panel.append(element("h1", "Не удалось открыть страницу"), element("p", error.message));
    const retry = element("button", "Повторить");
    retry.addEventListener("click", () => renderRoute(true));
    panel.append(retry);
    main.replaceChildren(panel);
    if (focus) main.focus({ preventScroll: true });
    overviewRequest?.then((overview) => {
      if (!signal.aborted) renderNavigation(overview.interns, overview.recent_intern_ids, id);
    }).catch(() => {});
  }
}

function focusSection(hash) {
  const section = document.getElementById(hash.slice(1));
  if (!section) return;
  section.focus({ preventScroll: true });
  section.scrollIntoView();
}

function navigate(path) {
  if (location.pathname === path) {
    if (location.hash) history.replaceState(null, "", path);
    window.scrollTo(0, 0);
    return;
  }
  history.pushState(null, "", path);
  window.scrollTo(0, 0);
  renderRoute(true);
}

document.addEventListener("click", (event) => {
  if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  const target = event.target.closest("a");
  if (!target) return;
  if (target.hasAttribute("data-route")) {
    event.preventDefault();
    navigate(target.pathname);
  } else if (target.getAttribute("href")?.startsWith("#")) {
    event.preventDefault();
    if (location.hash !== target.hash) history.pushState(null, "", target.hash);
    focusSection(target.hash);
  }
});
mobileIntern.addEventListener("change", () => navigate(mobileIntern.value ? internPath(mobileIntern.value) : "/"));
window.addEventListener("popstate", () => {
  if (location.pathname !== activePath) renderRoute(true);
  else if (location.hash) focusSection(location.hash);
});
renderRoute();
