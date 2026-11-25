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
  if (value / scale < .6) return { tone: "rose", label: "Низкая оценка" };
  if (value / scale < .8) return { tone: "amber", label: "Средняя оценка" };
  return { tone: "green", label: "Высокая оценка" };
}

function coloredScore(value, scale) {
  const quality = rating(value, scale);
  const mark = element("span", score(value, scale), "score-pill");
  if (quality) {
    mark.dataset.tone = quality.tone;
    mark.title = quality.label;
  }
  return mark;
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

function renderNavigation(interns, id) {
  navIds = interns.map((intern) => intern.id);
  directoryNav.replaceChildren(element("p", "Стажёры", "sidebar-label"));
  mobileIntern.replaceChildren(new Option("Выберите профиль", ""));
  for (const internId of navIds) {
    directoryNav.append(link(internId, internPath(internId), "nav-link"));
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
    const measured = latest?.value ?? null;
    const value = element("div", measured === null ? "—" : format.format(measured), "metric-value");
    if (latest) value.append(element("small", " / " + metric.scale));
    const subtitle = latest ? metric.source + " · мес. " + latest.month + " · " + responseLabel(latest.responses)
      : metric.source + " · нет оценки";
    const quality = rating(measured, metric.scale);
    if (quality) card.dataset.tone = quality.tone;
    card.append(element("h2", metric.label), value, element("p", subtitle));
    card.append(element("p", changeLabel(metric.change), "metric-change"));
    grid.append(card);
  }
}

function renderDirectory(page, interns) {
  page.querySelector(".directory").hidden = false;
  page.querySelector(".directory-jump").hidden = false;
  const list = page.querySelector(".directory-list");
  const heading = element("div", undefined, "directory-header");
  heading.setAttribute("aria-hidden", "true");
  for (const title of ["Стажёр", "Оценка программы", "Рекомендация к найму", "Прогресс по оценке наставников"]) {
    heading.append(element("span", title));
  }
  list.append(heading);
  for (const intern of interns) {
    const row = link(undefined, internPath(intern.id), "directory-row");
    const identity = element("div");
    identity.append(element("strong", intern.id), element("small", month(intern.month)));
    const satisfaction = element("div");
    satisfaction.append(element("small", "Удовлетворённость", "row-label"), coloredScore(intern.satisfaction, 5));
    const readiness = element("div");
    readiness.append(element("small", "Рекомендация к найму", "row-label"), coloredScore(intern.readiness, 10));
    if (intern.mentor_month !== null) readiness.append(element("small", "Наставник · " + month(intern.mentor_month).toLowerCase()));
    const progress = element("div", undefined, "row-progress");
    const dynamics = changeLabel(intern.progress);
    progress.append(element("small", "Прогресс по оценке наставников", "row-label"), element("span", dynamics));
    const arrow = element("span", "›");
    arrow.setAttribute("aria-hidden", "true");
    row.append(identity, satisfaction, readiness, progress, arrow);
    list.append(row);
  }
}

function commentCard(comment) {
  const article = element("article");
  const attribution = month(comment.month) + (comment.mentor ? " · " + comment.mentor : "");
  article.append(element("p", attribution, "comment-meta"), element("p", comment.text));
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

function renderMainChart(page, data, profile, signal) {
  const chart = profile ? data.charts[0] : data.charts.find(({ id }) => id === "readiness");
  page.querySelector("#chart-heading").textContent = profile ? "Удовлетворённость по месяцам" : "Рекомендация к найму по месяцам";
  const caption = page.querySelector(".chart-panel .chart-caption");
  caption.textContent = describeSeries(chart);
  const { traces, layout } = trendFigure(chart);
  drawChart(page.querySelector(".chart"), traces, layout, signal);
}

function renderMonthly(page, charts) {
  const months = charts[0].series[0].points.map((point) => String(point.month));
  const rows = charts.flatMap((chart) => chart.series.map((series) => {
    const source = chart.series.length > 1 ? " · " + series.label : "";
    const unit = chart.scale ? chart.scale.join("–") : chart.unit;
    return [chart.label + source + (unit ? " (" + unit + ")" : ""),
      ...series.points.map(({ value }) => value === null ? "—" : format.format(value))];
  }));
  const table = valuesTable("Все показатели по месяцам", ["Показатель / месяц", ...months], rows);
  table.classList.add("monthly-table");
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
    for (const value of values) row.insertCell().textContent = value;
  }
  return table;
}

function renderAdditionalCharts(page, data, isProfile, signal) {
  page.querySelector("#chart-section-heading").textContent = isProfile ? "Профиль и оценки наставника" : "Динамика и наставничество";
  const grid = page.querySelector(".chart-grid");
  const axes = { fixedrange: true, gridcolor: "#eaedf1", zeroline: false };

  function panel(title, caption, traces, layout, table) {
    const card = element("section", undefined, "panel secondary-chart");
    const graph = element("div", undefined, "chart");
    graph.setAttribute("aria-hidden", "true");
    card.append(element("h3", title), element("p", caption, "chart-caption"), graph);
    if (table) {
      const wrap = element("div", undefined, "table-scroll chart-values");
      wrap.append(table);
      card.append(wrap);
    }
    if (!table) {
      const tableLink = element("a", "Помесячные значения", "chart-table-link");
      tableLink.href = "#monthly";
      card.append(tableLink);
    }
    grid.append(card);
    drawChart(graph, traces, layout, signal);
  }

  if (!isProfile) {
    for (const id of ["satisfaction", "progress"]) {
      const trend = data.charts.find((item) => item.id === id);
      const { traces, layout } = trendFigure(trend);
      panel(trend.label + " по месяцам", describeSeries(trend), traces, layout);
    }
    const chart = data.charts.find(({ id }) => id === "hours");
    const points = chart.series[0].points;
    panel("Время наставничества", describeSeries(chart), points.some(({ value }) => value !== null) ? [{
      type: "bar", x: points.map(({ month }) => month), y: points.map(({ value }) => value),
      marker: { color: palette.blue, cornerradius: 5 }, hovertemplate: "Месяц %{x} · %{y} ч<extra></extra>",
    }] : [], {
      xaxis: { ...axes, dtick: 1, showgrid: false, title: { text: "Месяц" } },
      yaxis: { ...axes, rangemode: "tozero", ticksuffix: " ч" },
    });

    const groups = data.readiness_distribution;
    const count = groups.reduce((sum, group) => sum + group.count, 0);
    panel("Распределение рекомендаций к найму", "Оценки наставников за весь период · " + responseLabel(count) + ". Числа по диапазонам приведены ниже.", count ? [{
      type: "pie", hole: .68, sort: false, labels: groups.map((group) => group.label),
      values: groups.map((group) => group.count), textinfo: "none",
      marker: { colors: [palette.rose, palette.amber, palette.green], line: { width: 2, color: "#fff" } },
      hovertemplate: "%{label} баллов · %{value} (%{percent})<extra></extra>",
    }] : [], {
      margin: { t: 9, b: 44, l: 0, r: 0 }, showlegend: true,
      legend: { orientation: "h", x: .5, xanchor: "center", y: -.05, font: { size: 11 } },
      annotations: [{ text: String(count), x: .5, y: .5, showarrow: false, font: { size: 25, color: "#1d1d1f" } }],
    }, valuesTable("Распределение рекомендаций к найму", ["Баллы", "Число оценок"],
      groups.map((group) => [group.label, group.count])));
    return;
  }

  const abbreviations = ["Удовлетв.", "Ясность задач", "Поддержка", "Прогресс", "Мотивация"];
  const months = data.response_months;
  const labels = months.map((value) => month(value));
  const comparison = [];
  for (const [index, key] of (months[0] === months[1] ? [[1, "last"]] : [[0, "first"], [1, "last"]])) {
    const values = data.response_profile.map((axis) => axis[key]);
    if (values.filter((value) => value !== null).length < 3) continue;
    comparison.push({
      type: "scatterpolar", mode: "lines+markers", name: labels[index],
      r: [...values, values[0]], theta: [...abbreviations, abbreviations[0]],
      line: { color: index === 0 ? palette.violet : palette.blue, width: 2 },
      marker: { size: 6 }, fill: values.includes(null) ? "none" : "toself",
      fillcolor: index === 0 ? "rgba(128,80,220,.12)" : "rgba(0,117,237,.15)",
      hovertemplate: "%{theta} · %{r} / 5<extra>%{fullData.name}</extra>",
    });
  }
  const sameMonth = months[0] === months[1];
  panel("Самооценка стажёра", sameMonth ? "Самооценка за единственный доступный месяц · шкала 1–5" :
    "Самооценка в первом и последнем доступных месяцах · шкала 1–5", comparison, {
    margin: { t: 28, r: 52, b: 54, l: 52 }, showlegend: true,
    legend: { orientation: "h", x: .5, xanchor: "center", y: -.14 },
    polar: { radialaxis: { range: [0, 5], dtick: 1, showticklabels: false, gridcolor: "#eaedf1" },
      angularaxis: { tickfont: { size: 10 }, gridcolor: "#eaedf1" } },
  }, valuesTable("Самооценка стажёра", ["Показатель", ...(sameMonth ? [labels[1]] : labels)],
    data.response_profile.map((axis) => [axis.label, ...(sameMonth ? [score(axis.last, 5)] :
      [score(axis.first, 5), score(axis.last, 5)])])));

  const chart = data.charts.find(({ id }) => id === "readiness");
  const points = chart.series[0].points;
  panel("Рекомендация к найму по месяцам", describeSeries(chart), points.some(({ value }) => value !== null) ? [{
    type: "scatter", mode: "markers", x: points.map(({ month }) => month), y: points.map(({ value }) => value),
    marker: { size: 12, color: points.map(({ value }) => palette[rating(value, 10)?.tone || "neutral"]),
      line: { width: 1, color: "#575366" } },
    hovertemplate: "Месяц %{x} · %{y} / 10<extra></extra>",
  }] : [], {
    xaxis: { ...axes, dtick: 1, showgrid: false, title: { text: "Месяц" } },
    yaxis: { ...axes, range: [-.4, 10.5], dtick: 2 },
  });
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

function renderEvidence(page, data, profile) {
  const list = page.querySelector(".analysis-evidence ul");
  const metrics = [...data.metrics];
  if (profile && data.mentor_progress) {
    metrics.push({ label: "Прогресс в обучении", source: "Оценка наставников", scale: 5, change: data.mentor_progress });
  }
  for (const metric of metrics) {
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
    renderNavigation(overview.interns, id);
    const page = template.content.cloneNode(true).firstElementChild;
    const title = id ? "Стажёр " + id : "Обзор программы";
    document.title = title + " · МГТС";
    page.querySelector("h1").textContent = title;
    page.querySelector(".page-meta").textContent = profile ? "Последний ответ стажёра · " + month(profile.month).toLowerCase()
      : "Месяцы " + overview.first_month + "–" + overview.last_month + " · Стажёры: " + overview.intern_count +
        " (" + responseLabel(overview.intern_responses) + ") · Наставники: " +
        overview.mentor_count + " (" + responseLabel(overview.mentor_responses) + ")";
    const data = profile || overview;
    page.classList.toggle("profile", Boolean(profile));
    renderMetrics(page, data.metrics, Boolean(profile));
    renderMonthly(page, data.charts);
    if (profile) renderComments(page, profile);
    else renderDirectory(page, overview.interns);
    main.replaceChildren(page);
    renderMainChart(page, data, profile, signal);
    renderAdditionalCharts(page, data, Boolean(profile), signal);
    renderEvidence(page, data, profile);
    renderAnalysis(page, id, data, signal);
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
      if (!signal.aborted) renderNavigation(overview.interns, id);
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
