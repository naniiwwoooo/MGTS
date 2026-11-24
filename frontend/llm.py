"""Заготовка для будущей интеграции LLM-анализа.

Сейчас модуль не вызывает внешних сервисов. Он собирает компактный контекст
из таблиц и возвращает текстовую заглушку. Чтобы подключить реальную модель,
достаточно реализовать ``_call_model`` (например, через OpenAI/Anthropic API),
не меняя остальной код дашборда.
"""

from __future__ import annotations

import os

import pandas as pd

from frontend import data_loader as dl

DEFAULT_PROMPT_HEADER = (
    "Ты — аналитик HR-данных. На основе результатов опросов стажёров и "
    "наставников за 6 месяцев напиши краткое общее впечатление: динамика, "
    "сильные стороны, зоны риска и рекомендации. Пиши по-русски, дружелюбно и "
    "по делу."
)


def llm_available() -> bool:
    """Есть ли ключ для будущей интеграции."""
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
    """Точка расширения: здесь будет вызов LLM API."""
    raise NotImplementedError(
        "LLM-интеграция пока не подключена. Реализуйте _call_model() и задайте LLM_API_KEY."
    )


def generate_overall_impression(
    intern_df: pd.DataFrame, mentor_df: pd.DataFrame, model: str | None = None
) -> str:
    """Возвращает общее впечатление.

    Пока модель не подключена, отдаёт заранее сформированную заглушку, чтобы
    интерфейс можно было показать и протестировать.
    """
    if llm_available():
        return _call_model(build_prompt(intern_df, mentor_df), model=model)

    metrics = dl.overall_metrics(intern_df, mentor_df)
    return (
        "AI-анализ появится позже. "
        f"Уже сейчас видно: {metrics['interns']} стажёров и {metrics['mentors']} наставников "
        f"прошли {metrics['months']} месяцев программы. Средняя удовлетворённость стажёров — "
        f"{metrics['intern_satisfaction']}/5, готовность к найму — {metrics['hire_readiness']}/10."
    )
