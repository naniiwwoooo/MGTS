"""Пакет LLM-анализа (вынесен из frontend/llm.py)."""

from .core import (
    DEFAULT_PROMPT_HEADER,
    INTERN_PROMPT_HEADER,
    llm_available,
    build_context,
    build_prompt,
    build_intern_context,
    build_intern_prompt,
    _call_model,
    generate_overall_impression,
    generate_intern_impression,
)

__all__ = [
    "DEFAULT_PROMPT_HEADER",
    "INTERN_PROMPT_HEADER",
    "llm_available",
    "build_context",
    "build_prompt",
    "build_intern_context",
    "build_intern_prompt",
    "_call_model",
    "generate_overall_impression",
    "generate_intern_impression",
]
