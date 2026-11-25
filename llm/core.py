"""Интеграция LLM-анализа для дашборда стажёрской программы.

Поддерживаются два провайдера:

* **GigaChat** (по умолчанию) — OAuth-токен ``/api/v2/oauth`` + ``/chat/completions``;
* **OpenAI-совместимые API** (OpenRouter, Ollama и др.) — Bearer-токен + ``/chat/completions``.

Настройки берутся из переменных окружения и файла ``llm/.env``.
Если ключ не задан, дашборд показывает текстовую заглушку.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend import data_loader as dl  # noqa: E402

DEFAULT_PROMPT_HEADER = (
    "Ты — аналитик HR-данных. На основе результатов опросов стажёров и "
    "наставников за 6 месяцев напиши краткое общее впечатление: динамика, "
    "сильные стороны, зоны риска и рекомендации. Пиши по-русски, дружелюбно и "
    "по делу."
)

INTERN_PROMPT_HEADER = (
    "Ты — аналитик HR-данных. Ниже результаты опроса конкретного стажёра за "
    "6 месяцев, оценки наставников и их комментарии. Напиши краткое общее "
    "впечатление о стажёре: динамика, сильные стороны, зоны роста и "
    "рекомендации наставнику. Пиши по-русски, дружелюбно и по делу."
)

ENV_PATH = Path(__file__).resolve().parent / ".env"

# Кэш access token GigaChat (токен живёт ~30 минут).
_GIGACHAT_TOKEN: dict[str, object] = {"token": None, "expires_at": 0.0}

# Кэш успешных ответов модели (чтобы не дёргать API на каждый перерендер).
_IMPRESSION_CACHE: dict[str, str] = {}

# Приоритет моделей GigaChat, если заданная в LLM_MODEL недоступна.
GIGACHAT_MODEL_PREFERENCE = (
    "GigaChat-2",
    "GigaChat-2-Pro",
    "GigaChat-2-Max",
    "GigaChat-3-Ultra",
)


def _load_env() -> None:
    """Подгружает переменные из llm/.env (стандартными средствами, без dotenv)."""
    if not ENV_PATH.exists():
        return
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


def _getenv(*names: str) -> str | None:
    """Возвращает первое непустое значение среди перечисленных переменных."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def llm_available() -> bool:
    """Есть ли ключ/креды для обращения к LLM."""
    _load_env()
    return bool(
        _getenv(
            "GIGACHAT_CREDENTIALS",
            "GIGACHAT_API_KEY",
            "LLM_API_KEY",
            "OPENAI_API_KEY",
        )
    )


def build_context(intern_df: pd.DataFrame, mentor_df: pd.DataFrame) -> str:
    """Формирует текстовый контекст для модели из обеих таблиц."""
    metrics = dl.overall_metrics(intern_df, mentor_df)
    lines = [
        "Сводные показатели:",
        f"- Стажёров: {metrics['interns']}, наставников: {metrics['mentors']}, месяцев: {metrics['months']}",
        f"- Средняя удовлетворённость стажёров: {metrics['intern_satisfaction']}/5",
        f"- Средняя удовлетворённость наставников: {metrics['mentor_satisfaction']}/5",
        f"- Средний NPS стажёров: {metrics['avg_nps']}/10",
        f"- Средний прогресс (оценка наставников): {metrics['avg_progress']}/5",
        f"- Средняя готовность к найму: {metrics['hire_readiness']}/10",
        f"- Суммарные часы наставничества: {metrics['mentor_hours']}",
        "",
        "Средние ответы стажёров по месяцам:",
        dl.monthly_mean(intern_df, dl.INTERN_METRICS).round(2).to_string(index=False),
        "",
        "Средние оценки наставников по месяцам:",
        dl.monthly_mean(mentor_df, dl.MENTOR_METRICS + [dl.HIRE_READINESS]).round(2).to_string(index=False),
    ]
    return "\n".join(lines)


def build_prompt(intern_df: pd.DataFrame, mentor_df: pd.DataFrame) -> str:
    return f"{DEFAULT_PROMPT_HEADER}\n\n{build_context(intern_df, mentor_df)}"


def build_intern_context(
    intern_df: pd.DataFrame, mentor_df: pd.DataFrame, intern_id: str
) -> str:
    """Формирует текстовый контекст по конкретному стажёру.

    Включает ответы стажёра по месяцам, средние значения, оценки наставников
    и их комментарии.
    """
    timeline = dl.intern_timeline(intern_df, intern_id)
    if timeline.empty:
        return f"Стажёр: {intern_id}\nНет данных опроса по этому стажёру."

    averages = timeline[dl.INTERN_METRICS].mean()
    avg_nps = timeline[dl.NPS].mean()

    lines = [
        f"Стажёр: {intern_id}",
        "",
        "Средние ответы стажёра за 6 месяцев (1–5, NPS 0–10):",
        *[f"- {metric}: {averages[metric]:.2f}/5" for metric in dl.INTERN_METRICS],
        f"- NPS: {avg_nps:.1f}/10",
        "",
        "Ответы стажёра по месяцам:",
        timeline[[dl.MONTH, *dl.INTERN_METRICS, dl.NPS]].round(2).to_string(index=False),
    ]

    mentor_tl = dl.mentor_timeline(mentor_df, intern_id)
    if not mentor_tl.empty:
        lines += [
            "",
            "Оценки наставников по месяцам:",
            mentor_tl[[dl.MONTH, "Прогресс стажёра", dl.HIRE_READINESS]]
            .round(2)
            .to_string(index=False),
        ]

    comments = dl.mentor_comments(mentor_df, intern_id)
    if not comments.empty:
        lines += ["", "Комментарии наставников:"]
        for _, item in comments.iterrows():
            lines.append(
                f"- Месяц {int(item[dl.MONTH])}, наставник {item[dl.MENTOR_ID]}: "
                f"{item[dl.COMMENT]}"
            )

    return "\n".join(lines)


def build_intern_prompt(
    intern_df: pd.DataFrame, mentor_df: pd.DataFrame, intern_id: str
) -> str:
    return f"{INTERN_PROMPT_HEADER}\n\n{build_intern_context(intern_df, mentor_df, intern_id)}"


def _ssl_context() -> ssl.SSLContext:
    """Контекст без проверки сертификата.

    GigaChat использует сертификаты НУЦ Минцифры, которых обычно нет в
    системном хранилище. Для локального запуска проверку отключаем
    (аналогично ``verify_ssl_certs=False`` в официальном SDK).
    """
    return ssl._create_unverified_context()


def _gigachat_token(auth_key: str, auth_url: str, scope: str, timeout: int) -> str:
    """Получает (с кэшированием) access token GigaChat по ключу авторизации."""
    now = time.time()
    cached = _GIGACHAT_TOKEN.get("token")
    expires_at = float(_GIGACHAT_TOKEN.get("expires_at") or 0.0)
    if cached and expires_at > now + 60:
        return str(cached)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {auth_key}",
    }
    data = urllib.parse.urlencode({"scope": scope}).encode("utf-8")
    req = urllib.request.Request(auth_url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GigaChat OAuth ошибка {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось получить токен GigaChat: {exc}") from exc

    token = body.get("access_token")
    if not token:
        raise RuntimeError(f"GigaChat не вернул access_token: {body}")

    expires_ms = body.get("expires_at")
    try:
        expires_sec = float(expires_ms) / 1000.0 if expires_ms else now + 1800
    except (TypeError, ValueError):
        expires_sec = now + 1800

    _GIGACHAT_TOKEN["token"] = token
    _GIGACHAT_TOKEN["expires_at"] = expires_sec
    return token


def _gigachat_models(base_url: str, token: str, timeout: int) -> list[str]:
    """Возвращает доступные генеративные модели (по приоритету), запрашивая /models."""
    req = urllib.request.Request(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError):
        return []

    ids = [item.get("id") for item in body.get("data", []) if item.get("id")]
    ordered = [m for m in GIGACHAT_MODEL_PREFERENCE if m in ids]
    rest = [m for m in ids if m not in ordered and "embedding" not in m.lower()]
    return ordered + rest


def _gigachat_chat_raw(
    base_url: str,
    token: str,
    model_name: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> dict:
    """Один запрос к /chat/completions. Пробрасывает HTTPError/URLError наружу."""
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _call_gigachat(prompt: str, model: str | None, timeout: int) -> str:
    """Запрос к GigaChat API (токен OAuth + /chat/completions).

    Если заданная модель недоступна (например, устаревший ``GigaChat``),
    автоматически подбирает рабочую модель из ``/models`` и повторяет запрос.
    """
    auth_key = _getenv("GIGACHAT_CREDENTIALS", "GIGACHAT_API_KEY", "LLM_API_KEY")
    if not auth_key:
        raise RuntimeError("Не задан ключ авторизации GigaChat (GIGACHAT_CREDENTIALS / LLM_API_KEY)")

    base_url = (os.getenv("LLM_BASE_URL") or "https://api.giga.chat/v1").rstrip("/")
    auth_url = os.getenv("LLM_AUTH_URL") or "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    scope = os.getenv("LLM_SCOPE") or "GIGACHAT_API_PERS"
    model_name = model or os.getenv("LLM_MODEL") or "GigaChat-2"
    temperature = float(os.getenv("LLM_TEMPERATURE") or 0.3)
    max_tokens = int(os.getenv("LLM_MAX_TOKENS") or 700)

    token = _gigachat_token(auth_key, auth_url, scope, timeout)
    messages = [
        {"role": "system", "content": "Ты — аналитик HR-данных. Отвечай по-русски, кратко и по делу."},
        {"role": "user", "content": prompt},
    ]

    tried: list[str] = []
    candidates: list[str] = [model_name]
    last_error: str | None = None

    while candidates:
        current = candidates.pop(0)
        if current in tried:
            continue
        tried.append(current)
        try:
            body = _gigachat_chat_raw(
                base_url, token, current, messages, temperature, max_tokens, timeout
            )
            choices = body.get("choices")
            if not choices:
                raise RuntimeError(f"GigaChat вернул пустой ответ: {body}")
            return choices[0]["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = f"GigaChat API ошибка {exc.code}: {detail}"
            # Модель не найдена/недоступна — пробуем доступные из /models.
            if exc.code in (400, 404) and "model" in detail.lower():
                if not candidates:
                    candidates = [m for m in _gigachat_models(base_url, token, timeout) if m not in tried]
                continue
            raise RuntimeError(last_error) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Не удалось соединиться с GigaChat: {exc}") from exc

    raise RuntimeError(last_error or "GigaChat: не удалось подобрать доступную модель")


def _call_openai_compatible(prompt: str, model: str | None, timeout: int) -> str:
    """Запрос к OpenAI-совместимому API (OpenRouter, Ollama и др.)."""
    api_key = _getenv("LLM_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Не задан LLM_API_KEY / OPENAI_API_KEY")

    base_url = (os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    model_name = model or os.getenv("LLM_MODEL") or "nvidia/nemotron-3.5-lightning:free"
    temperature = float(os.getenv("LLM_TEMPERATURE") or 0.3)
    max_tokens = int(os.getenv("LLM_MAX_TOKENS") or 700)

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Ты — аналитик HR-данных. Отвечай по-русски, кратко и по делу."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://mgts.local/dashboard",
            "X-Title": "MGTS Intern Dashboard",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API ошибка {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось соединиться с API: {exc}") from exc

    choices = body.get("choices")
    if not choices:
        raise RuntimeError(f"API вернул пустой ответ: {body}")
    return choices[0]["message"]["content"].strip()


def _use_gigachat() -> bool:
    """Определяет провайдера. По умолчанию — GigaChat."""
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    base_url = (os.getenv("LLM_BASE_URL") or "").lower()
    if "giga" in provider or "giga" in base_url:
        return True
    if _getenv("GIGACHAT_CREDENTIALS", "GIGACHAT_API_KEY"):
        return True
    if provider in {"openai", "openrouter", "openai-compatible", "ollama"}:
        return False
    return True


def _call_model(prompt: str, model: str | None = None) -> str:
    """Вызов модели. Провайдер выбирается через ``LLM_PROVIDER`` (по умолчанию GigaChat)."""
    _load_env()
    timeout = int(os.getenv("LLM_TIMEOUT") or 60)
    if _use_gigachat():
        return _call_gigachat(prompt, model, timeout)
    return _call_openai_compatible(prompt, model, timeout)


def generate_overall_impression(
    intern_df: pd.DataFrame, mentor_df: pd.DataFrame, model: str | None = None
) -> str:
    """Возвращает общее впечатление от ИИ.

    Если модель доступна, запрашивает её через выбранного провайдера (по
    умолчанию GigaChat). При любой ошибке (нет ключа, сеть, SSL, ответ API)
    возвращает понятную строку, чтобы дашборд не падал.
    """
    if not llm_available():
        metrics = dl.overall_metrics(intern_df, mentor_df)
        return (
            "AI-анализ появится позже. "
            f"Уже сейчас видно: {metrics['interns']} стажёров и {metrics['mentors']} наставников "
            f"прошли {metrics['months']} месяцев программы. Средняя удовлетворённость стажёров — "
            f"{metrics['intern_satisfaction']}/5, готовность к найму — {metrics['hire_readiness']}/10."
        )

    try:
        prompt = build_prompt(intern_df, mentor_df)
        cache_key = f"{model or ''}\n{prompt}"
        cached = _IMPRESSION_CACHE.get(cache_key)
        if cached is not None:
            return cached
        result = _call_model(prompt, model=model)
        _IMPRESSION_CACHE[cache_key] = result
        return result
    except Exception as exc:  # noqa: BLE001
        return (
            "Не удалось получить ответ от ИИ-модели. "
            f"Причина: {exc}. Проверьте ключ GigaChat (LLM_API_KEY) и подключение к сети."
        )


def generate_intern_impression(
    intern_df: pd.DataFrame, mentor_df: pd.DataFrame, intern_id: str, model: str | None = None
) -> str:
    """Возвращает общее впечатление ИИ о конкретном стажёре.

    Передаёт модели ответы стажёра по месяцам, оценки наставников и их
    комментарии. Результат кэшируется; при любой ошибке возвращается понятная
    строка, чтобы дашборд не падал.
    """
    if not llm_available():
        return (
            f"AI-анализ по стажёру {intern_id} появится позже. "
            "Изучите динамику ответов и комментарии наставников ниже."
        )

    try:
        prompt = build_intern_prompt(intern_df, mentor_df, intern_id)
        cache_key = f"intern:{intern_id}:{model or ''}\n{prompt}"
        cached = _IMPRESSION_CACHE.get(cache_key)
        if cached is not None:
            return cached
        result = _call_model(prompt, model=model)
        _IMPRESSION_CACHE[cache_key] = result
        return result
    except Exception as exc:  # noqa: BLE001
        return (
            f"Не удалось получить ответ от ИИ-модели по стажёру {intern_id}. "
            f"Причина: {exc}. Проверьте ключ GigaChat (LLM_API_KEY) и подключение к сети."
        )
