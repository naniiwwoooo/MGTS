"""Заготовка для будущей интеграции LLM-анализа.

Логика перенесена в корневой пакет ``llm`` (``llm/core.py``).
Этот модуль оставлен как обратносовместимая обёртка: ``from frontend import llm``
продолжает работать, все имена реэкспортируются из ``llm``.
"""

from __future__ import annotations

from llm import (  # noqa: E402
    DEFAULT_PROMPT_HEADER,
    build_context,
    build_prompt,
    generate_overall_impression,
    llm_available,
    _call_model,
)

__all__ = [
    "DEFAULT_PROMPT_HEADER",
    "llm_available",
    "build_context",
    "build_prompt",
    "_call_model",
    "generate_overall_impression",
]
