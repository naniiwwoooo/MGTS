"""Чат по проверяемым фактам стажёрской программы."""

import asyncio
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

import llm

from .dashboard import Snapshot, overview, profile
from .models import Chart, Point


class Question(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)]
    version: str = Field(min_length=1, max_length=64)
    metric: str | None = Field(default=None, max_length=40)


class Evidence(BaseModel):
    label: str
    source: str
    row: str
    points: list[Point]
    scale: int | None = None
    unit: str | None = None


class Answer(BaseModel):
    status: Literal["answered", "clarify", "no_data", "out_of_scope"]
    text: str
    metric: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    source: Literal["monthly", "feedback"] | None = None
    anchor: str | None = None


TOPICS = {
    "development": r"прогресс|развити|обучени[еяю]",
    "satisfaction": r"удовлетвор[её]н|довольн",
    "clarity": r"понятност|понимани\w* задач|ожидани",
    "quality": r"качеств\w* (?:работ|выполнен|задач)",
    "workload": r"нагруз|загруз",
    "mentoring": r"поддержк\w* наставник|обратн\w* связ",
    "interest": r"интерес\w* к задач",
    "autonomy": r"самостоятельност",
    "deadlines": r"срок|организац\w* работ",
    "initiative": r"инициатив|вовлеч",
    "team": r"команд",
}
DEFINITIONS = {
    "development": "Профессиональное развитие — ответ стажера о развитии полезных навыков по шкале от 1 до 5.",
    "clarity": "Ответ стажера показывает ясность его задач. Наставник отдельно оценивает понимание стажером поставленных задач и результата. Обе шкалы от 1 до 5.",
}

MONTH_WORDS = {
    "перв": 1, "втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6,
    "седьм": 7, "восьм": 8, "девят": 9, "десят": 10, "одиннадцат": 11, "двенадцат": 12,
}
CALENDAR_MONTH = re.compile(r"\b(?:январ\w*|феврал\w*|март\w*|апрел\w*|ма[йея]|ию[нл]\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)\b")
MONTH = re.compile(r"(?<!\d)(\d{1,2})(?:-(?:й|го|му|м|ом))?(?=\s*мес)|мес\w*\s*(\d{1,2})(?!\d)")
BLOCKED = re.compile(
    r"игнорируй|системн\w* промпт|инструкц\w* модел|придумай|выдумай|отправь|"
    r"погод|рецепт|напиши код|секрет|парол|api.?key|кого нанять|кого уволить|стоит ли нанимать"
)


def number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def show_fact(fact: Evidence, count_only: bool) -> str:
    pieces = []
    for point in fact.points:
        if point.value is None:
            pieces.append(f"месяц {point.month} — нет данных")
            continue
        unit = f" из {fact.scale}" if fact.scale else (f" {fact.unit}" if fact.unit else "")
        total = f"ответов: {point.responses}"
        pieces.append(f"месяц {point.month} — " + (total if count_only else f"{number(point.value)}{unit} ({total})"))
    return f"{fact.label}, {fact.source}: " + "; ".join(pieces) + "."


def facts_for(charts: list[Chart], months: list[int], latest_only: bool, include_latest: bool) -> list[Evidence]:
    facts = []
    for chart in charts:
        for index, series in enumerate(chart.series):
            available = [point for point in series.points if point.value is not None]
            if months:
                indexed = {point.month: point for point in series.points}
                selected = set(months)
                if include_latest and available:
                    selected.add(available[-1].month)
                points = [indexed.get(month, Point(month=month, value=None, responses=0)) for month in sorted(selected)]
            elif latest_only:
                points = available[-1:]
            else:
                points = [available[0], available[-1]] if len(available) > 1 else available
            if points:
                facts.append(Evidence(
                    label=chart.label, source=series.label, row=f"{chart.id}-{index}",
                    points=points, scale=chart.scale[1] if chart.scale else None, unit=chart.unit,
                ))
    return facts


async def prioritize(facts: list[Evidence], lock: asyncio.Lock) -> list[Evidence]:
    """Модель выбирает порядок фактов. Текст ответа и числа формирует сервер."""
    if len(facts) < 2 or lock.locked() or not llm.llm_available():
        return facts
    candidates = [
        {"id": index, "показатель": fact.label, "источник": fact.source,
         "данные": [point.model_dump() for point in fact.points]}
        for index, fact in enumerate(facts)
    ]
    prompt = (
        "Ты помощник рекрутера по стажёрской программе. Упорядочь факты по полезности "
        "для обзора динамики. Используй только переданные данные. Верни только JSON-массив "
        "из всех исходных id, без повторов, пояснений и разметки.\n"
        + json.dumps(candidates, ensure_ascii=False)
    )
    try:
        async with lock:
            raw = await asyncio.to_thread(llm._call_model, prompt)
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw.strip(), flags=re.IGNORECASE | re.DOTALL)
        order = json.loads(fenced.group(1) if fenced else raw)
        if isinstance(order, list) and all(type(item) is int for item in order):
            if sorted(order) == list(range(len(facts))):
                return [facts[item] for item in order]
    except Exception:
        pass
    return facts


async def answer_question(snapshot: Snapshot, intern_id: str | None, message: Question, lock: asyncio.Lock) -> Answer:
    question = message.question.casefold().replace("ё", "е").strip()
    ids = re.findall(r"\b(?:int|ст)[- ]?\d+\b", question)
    if BLOCKED.search(question) or any(item.replace(" ", "-") != (intern_id or "").lower() for item in ids):
        return Answer(status="out_of_scope", text="Отвечаю только по данным открытой программы или профиля.")
    period = re.sub(r"за\s+(?:[1-6]|шесть)\s+месяцев", "", question)
    words = re.findall(r"\b\w+\b", period)
    ranged = re.search(r"с\s+(\d{1,2})(?:-го)?\s+(?:по|до)\s+(\d{1,2})(?:-й|-го)?\s+мес", question)
    months = [int(left or right) for left, right in MONTH.findall(period)]
    if ranged:
        months.extend(map(int, ranged.groups()))
    for word in words:
        for prefix, month in MONTH_WORDS.items():
            if word.startswith(prefix) and "месяц" in question:
                months.append(month)
                break
    months = sorted(set(months))
    topics = [key for key, expression in TOPICS.items() if re.search(expression, question)]
    if not topics and message.metric in TOPICS and re.match(r"^(?:а\s+|и\s+)?(?:в\s+\w+|за\s+\w+|сколько ответов|а последний)", question):
        topics = [message.metric]
    feedback = bool(re.search(r"отзыв|комментари", question))
    summary = bool(re.search(r"на каких цифрах|ии[- ]вывод|сводк|итог\w* программ|главн\w* изменен", question))
    comparative = period != question or bool(re.search(r"сравни|изменил|динамик|вырос|совпал|рост|снизи", question))
    count_only = bool(re.search(r"сколько ответов|число ответов|количество ответов", question))
    if re.search(r"\bnps\b|найм|час\w* наставнич", question):
        return Answer(status="no_data", text="В текущих анкетах нет такого показателя. Можно спросить об оценках опыта стажировки и оценках работы наставниками.")
    if not (topics or feedback or summary or count_only):
        return Answer(status="out_of_scope", text="Я отвечаю на вопросы об оценках, их динамике, числе ответов и отзывах в этом дашборде.")
    if CALENDAR_MONTH.search(question):
        return Answer(status="clarify", text="Опросы используют номера месяцев участия. Укажите месяц с первого по шестой.")
    if any(month < 1 or month > 6 for month in months):
        return Answer(status="no_data", text="В опросах предусмотрены месяцы участия с первого по шестой.")
    data = profile(snapshot, intern_id) if intern_id else overview(snapshot)
    if feedback:
        if not intern_id:
            return Answer(status="clarify", text="Откройте профиль нужного стажёра, чтобы посмотреть отзывы.")
        from_intern = bool(re.search(r"(?:отзыв|комментари)\w* стажер", question))
        comments = data.intern_comments if from_intern else data.comments
        found = next((item for item in comments if not months or item.month in months), None)
        if found:
            anchor = "fresh-feedback" if not from_intern and found.month == comments[0].month else "feedback"
            return Answer(status="answered", text=f"Месяц {found.month}. «{found.text}»", source="feedback", anchor=anchor)
        return Answer(status="no_data", text="За выбранный период комментариев нет.")
    if not topics and not summary:
        return Answer(status="clarify", text="Для какого показателя посчитать число ответов?")
    evidence_request = "на каких цифрах" in question or "ии-вывод" in question
    keys = topics or ["satisfaction", "development", "quality"]
    if evidence_request and intern_id and not topics:
        keys.append("autonomy")
    chart_ids = set(keys)
    if "clarity" in keys:
        chart_ids.add("expectations")
    if "team" in keys:
        chart_ids.add("collaboration")
    charts = [item for item in data.charts if item.id in chart_ids]
    include_latest = "последн" in question or (comparative and len(months) == 1 and bool(re.search(r"\bс\s+(?:перв|\d+)", question)))
    facts = facts_for(charts, months, not (comparative or summary), include_latest)
    definition = DEFINITIONS.get(topics[0]) if len(topics) == 1 else None
    explain = bool(re.search(r"что знач|что означ|как счита|как рассчит", question))
    if explain and definition:
        return Answer(status="answered", text=definition, metric=topics[0], evidence=facts, source="monthly")
    if not any(point.value is not None for fact in facts for point in fact.points):
        return Answer(status="no_data", text="В открытом разделе за выбранный период нет таких оценок.")
    if summary:
        facts = await prioritize(facts, lock)
    lines = [show_fact(fact, count_only) for fact in facts]
    if "совпал" in question and len(facts) == 2 and len(months) == 1:
        values = [fact.points[0].value for fact in facts]
        if all(value is not None for value in values):
            lines.insert(0, "Оценки совпали." if values[0] == values[1] else "Оценки различаются.")
    return Answer(
        status="answered", text="\n".join(lines),
        metric=topics[0] if len(topics) == 1 else None, evidence=facts, source="monthly",
    )
