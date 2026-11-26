const conversations = new Map();

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  if (className) element.className = className;
  return element;
}

export function renderAssistant(page, internId, version, signal) {
  const key = JSON.stringify([version, internId]);
  const conversation = conversations.get(key) || { messages: [], metric: null };
  conversations.delete(key);
  conversations.set(key, conversation);
  if (conversations.size > 12) conversations.delete(conversations.keys().next().value);

  const dialog = page.querySelector(".assistant-dialog");
  const launcher = page.querySelector(".assistant-open");
  const quickForm = page.querySelector(".assistant-launch");
  const quickInput = quickForm.querySelector("input");
  const form = dialog.querySelector("form");
  const input = form.querySelector("input");
  const submit = form.querySelector("button");
  const log = dialog.querySelector(".assistant-messages");
  const status = dialog.querySelector(".assistant-status");
  let busy = false;
  let opener = launcher;
  let destination = null;
  const scope = internId ? "Данные: стажёр " + internId : "Данные: обзор программы";
  page.querySelectorAll(".assistant-scope").forEach((item) => { item.textContent = scope; });

  function open(trigger) {
    if (dialog.open) return;
    opener = trigger;
    if (matchMedia("(max-width: 760px)").matches) dialog.showModal();
    else dialog.show();
    input.focus();
  }

  function renderMessage(message) {
    const item = node("article", "", message.user ? "assistant-user" : "");
    item.append(node("strong", message.user ? "Вы" : "Помощник"), node("p", message.text));
    const links = message.evidence?.map((fact) => ({
      label: fact.label + " · " + fact.source, id: "monthly-" + fact.row,
    })) || [];
    if (message.source === "feedback") {
      links.push({ label: "Комментарий в профиле", id: message.anchor || "feedback" });
    }
    for (const link of links) {
      const anchor = node("a", link.label);
      anchor.href = "#" + link.id;
      anchor.addEventListener("click", (event) => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        const target = document.getElementById(link.id);
        if (!target) return;
        destination = target;
        if (location.hash !== anchor.hash) history.pushState(null, "", anchor.hash);
        dialog.close();
      });
      item.append(anchor, document.createElement("br"));
    }
    log.append(item);
  }

  function add(message) {
    conversation.messages.push(message);
    renderMessage(message);
    if (conversation.messages.length > 16) {
      conversation.messages.shift();
      log.firstElementChild.remove();
    }
    log.scrollTop = log.scrollHeight;
  }

  async function ask(question) {
    if (busy || signal.aborted) return;
    question = question.trim();
    if (!question) return;
    busy = true;
    submit.disabled = true;
    input.value = "";
    status.textContent = "Проверяем данные опросов…";
    add({ user: true, text: question });
    const endpoint = internId ? "/api/interns/" + encodeURIComponent(internId) + "/assistant" : "/api/assistant/overview";
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, version, metric: conversation.metric }),
        signal,
      });
      if (signal.aborted) return;
      if (!response.ok) {
        if (response.status === 409) {
          status.textContent = "Опросы обновились. Обновите страницу, чтобы продолжить.";
          return;
        }
        throw new Error("Не удалось получить ответ.");
      }
      const result = await response.json();
      if (signal.aborted) return;
      if (result.metric) conversation.metric = result.metric;
      add(result);
      status.textContent = "";
    } catch {
      if (!signal.aborted) {
        status.textContent = "Не удалось получить ответ. Повторите отправку.";
        input.value = question;
      }
    } finally {
      busy = false;
      submit.disabled = false;
    }
  }

  conversation.messages.forEach(renderMessage);
  const examples = [
    "Как изменилось профессиональное развитие?",
    "На каких цифрах основан ИИ-вывод?",
    internId ? "Покажи последний отзыв наставника" : "Сколько ответов о понятности задач в шестом месяце?",
  ];
  const suggestions = dialog.querySelector(".assistant-suggestions");
  for (const question of examples) {
    const button = node("button", question);
    button.type = "button";
    button.addEventListener("click", () => ask(question));
    suggestions.append(button);
  }

  launcher.addEventListener("click", () => open(launcher));
  const mobile = page.querySelector(".assistant-mobile");
  mobile.addEventListener("click", () => open(mobile));
  quickForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (busy || !quickInput.value.trim()) return;
    open(quickInput);
    ask(quickInput.value);
    quickInput.value = "";
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    ask(input.value);
  });
  dialog.querySelector(".assistant-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      dialog.close();
    }
  });
  dialog.addEventListener("close", () => {
    if (signal.aborted) return;
    if (destination) {
      destination.focus({ preventScroll: true });
      destination.scrollIntoView();
      destination = null;
    } else {
      opener.focus();
    }
  });
  signal.addEventListener("abort", () => {
    if (dialog.open) dialog.close();
  }, { once: true });
}
