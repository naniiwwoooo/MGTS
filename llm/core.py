"""Заготовка для будущей интеграции LLM-анализа.

Содержимое перенесено из ``frontend/llm.py`` в корневой пакет ``llm``.
Модуль не вызывает внешних сервисов. Он собирает компактный контекст
из таблиц и возвращает текстовую заглушку. Чтобы подключить реальную модель,
достаточно реализовать ``_call_model`` (например, через OpenAI/Anthropic API),
не меняя остальной код дашборда.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
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


ENV_PATH = Path(__file__).resolve().parent / ".env"


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


def llm_available() -> bool:
    """Есть ли ключ для будущей интеграции."""
    _load_env()
    return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


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


def _call_model(prompt: str, model: str | None = None) -> str:
    """Вызов модели через OpenRouter (OpenAI-совместимый API).

    По умолчанию используется ``nvidia/nemotron-3.5-lightning:free``.
    Ключ берётся из переменной окружения ``LLM_API_KEY`` или ``OPENAI_API_KEY``.
    """
    _load_env()
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Не задан LLM_API_KEY / OPENAI_API_KEY для OpenRouter")

    model_name = model or "nvidia/nemotron-3.5-lightning:free"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Ты — аналитик HR-данных. Отвечай по-русски, кратко и по делу."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
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
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter API ошибка {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось соединиться с OpenRouter: {exc}") from exc

    choices = body.get("choices")
    if not choices:
        raise RuntimeError(f"OpenRouter вернул пустой ответ: {body}")

    return choices[0]["message"]["content"].strip()


def generate_overall_impression(
    intern_df: pd.DataFrame, mentor_df: pd.DataFrame, model: str | None = None
) -> str:
    """Возвращает общее впечатление.

    Если модель доступна, запрашивает её через OpenRouter. При любой ошибке
    (нет ключа, сеть, SSL, ответ API) возвращает понятную строку, чтобы
    дашборд не падал.
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
        return _call_model(build_prompt(intern_df, mentor_df), model=model)
    except Exception as exc:  # noqa: BLE001
        return (
            "Не удалось получить ответ от ИИ-модели. "
            f"Причина: {exc}. Проверьте переменную LLM_API_KEY / OPENAI_API_KEY и подключение к сети."
        )
