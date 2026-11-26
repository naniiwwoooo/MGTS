"""Генерация и кэширование выводов модели."""

import asyncio
import os
import re
import ssl
import urllib.error
from collections import OrderedDict
from datetime import datetime, timezone

import llm

from . import dashboard
from .dashboard import Snapshot
from .models import Analysis

PROMPT_INSTRUCTIONS = (
    "Ты HR-эксперт. Дай рекрутеру краткое заключение по подготовленным фактам, "
    "до 100 слов, без вопросов и заданий. Опиши главную динамику, опираясь на указанные направления. "
    "Различай ответы стажёров и оценки наставников по различным вопросам. "
    "Не давай решения о найме. Не делай выводов о причинах "
    "и не утверждай, что тренд был устойчивым, если доступны только края периода. "
    "Не повторяй числа и даты: интерфейс показывает их отдельно. "
    "Не используй проценты, кратность и выражения вроде «вдвое» или «благодаря». "
    "Один абзац на русском языке из двух-трёх утвердительных предложений."
)
CONFIG_KEYS = (
    "LLM_PROVIDER", "LLM_BASE_URL", "LLM_SCOPE", "LLM_MODEL",
    "LLM_TEMPERATURE", "LLM_MAX_TOKENS", "LLM_AUTH_URL", "LLM_CA_FILE",
)


UNSUPPORTED_CLAIMS = re.compile(
    r"[?\d]|\b(?:благодаря|вследствие|поэтому|из[-‑ ]за|вдвое|втрое|удво\w*|утро\w*|процент\w*)\b",
    re.IGNORECASE,
)


def analysis_error(error: Exception) -> str:
    """Возвращает подсказку без тела ответа провайдера и локальных путей."""
    cause = error
    while cause is not None:
        if isinstance(cause, urllib.error.HTTPError):
            if cause.code in (401, 403):
                return "Провайдер отклонил авторизацию. Проверьте ключ и доступ к модели."
            if cause.code == 429:
                return "Провайдер временно ограничил запросы. Попробуйте чуть позже."
        if isinstance(cause, urllib.error.URLError):
            if isinstance(cause.reason, ssl.SSLCertVerificationError):
                return "Не удалось проверить сертификат провайдера. Проверьте настройки TLS."
            return "Нет соединения с провайдером. Попробуйте ещё раз."
        if isinstance(cause, TimeoutError):
            return "Провайдер не ответил вовремя. Попробуйте ещё раз."
        cause = cause.__cause__
    return "Не удалось получить вывод от модели. Попробуйте ещё раз."


class AnalysisService:
    def __init__(self) -> None:
        self.results: OrderedDict[tuple, Analysis] = OrderedDict()
        self.pending: dict[tuple, asyncio.Task] = {}
        self.provider_lock = asyncio.Lock()

    def key(self, snapshot: Snapshot, intern_id: str | None) -> tuple:
        return snapshot.version, intern_id, tuple(os.getenv(name) for name in CONFIG_KEYS)

    def status(self, snapshot: Snapshot, intern_id: str | None) -> Analysis:
        available = llm.llm_available()
        key = self.key(snapshot, intern_id)
        if key in self.pending:
            return Analysis(status="running")
        return self.results.get(key) or Analysis(status="available" if available else "unavailable")

    def start(self, snapshot: Snapshot, intern_id: str | None, refresh: bool) -> Analysis:
        if not llm.llm_available():
            return Analysis(status="unavailable")

        key = self.key(snapshot, intern_id)
        if key in self.pending:
            return Analysis(status="running")
        cached = self.results.get(key)
        if not refresh and cached and cached.status == "ready":
            return cached
        self.pending[key] = asyncio.create_task(self.generate(key, snapshot, intern_id))
        return Analysis(status="running")

    async def generate(self, key: tuple, snapshot: Snapshot, intern_id: str | None) -> None:
        try:
            if intern_id is None:
                data = dashboard.overview(snapshot)
                scope = "Сводные показатели программы."
                metrics = data.metrics
            else:
                data = dashboard.profile(snapshot, intern_id)
                scope = "Показатели одного стажёра."
                metrics = data.metrics

            facts = []
            directions = []
            for metric in metrics:
                if metric.change is None:
                    continue
                first, latest = metric.change.first, metric.change.latest
                label = f"{metric.label} · {metric.source}"
                if metric.participants:
                    facts.append(
                        f"{label}: средняя по последней доступной оценке каждого стажера "
                        f"{metric.value:.2f}/{metric.scale}, стажеров с оценкой: {metric.participants}."
                    )
                current = f"месяц {latest.month}: {latest.value:.2f}/{metric.scale}, ответов: {latest.responses}"
                if first.month == latest.month:
                    facts.append(f"{label}: {current}; для сравнения недостаточно данных.")
                    directions.append(f"{label}: для сравнения недостаточно данных.")
                    continue
                if latest.value > first.value:
                    direction = "рост"
                elif latest.value < first.value:
                    direction = "снижение"
                else:
                    direction = "без изменений"
                directions.append(f"{label}: {direction} между первой и последней оценками.")
                facts.append(
                    f"{label}: месяц {first.month}: {first.value:.2f}/{metric.scale}, ответов: {first.responses}; "
                    f"{current}; {direction} между этими месяцами."
                )
            if not facts:
                raise ValueError("В опросах нет оценок для вывода")
            if intern_id is not None:
                facts.extend(f"Сигнал локальных правил: {signal.label} ({signal.detail})"
                             for signal in data.signals[:6])
            else:
                with_signals = sum(bool(item.signals) for item in data.interns)
                repeated = sum(any(signal.source == "feedback" for signal in item.signals) for item in data.interns)
                facts.append(f"Стажеров с сигналами за весь период: {with_signals} из {data.intern_count}. "
                             f"С повторяющимися темами в комментариях: {repeated}.")
            prompt = f"{PROMPT_INSTRUCTIONS}\n{scope}\n" + "\n".join(facts)
            async with self.provider_lock:
                text = (await asyncio.to_thread(llm._call_model, prompt)).strip()
                if not text or UNSUPPORTED_CLAIMS.search(text):
                    correction = "Опиши только указанные изменения без причин и сравнений по величине.\n"
                    retry = f"{correction}{PROMPT_INSTRUCTIONS}\n{scope}\n" + "\n".join(directions)
                    text = (await asyncio.to_thread(llm._call_model, retry)).strip()
            if not text or UNSUPPORTED_CLAIMS.search(text):
                raise ValueError("Модель не вернула готовое заключение")
            result = Analysis(status="ready", text=text, generated_at=datetime.now(timezone.utc))
        except Exception as exc:
            previous = self.results.get(key)
            result = Analysis(
                status="error",
                text=previous.text if previous else None,
                generated_at=previous.generated_at if previous else None,
                error_message=analysis_error(exc),
            )
        finally:
            self.pending.pop(key, None)
        self.results[key] = result
        self.results.move_to_end(key)
        while len(self.results) > 32:
            self.results.popitem(last=False)
