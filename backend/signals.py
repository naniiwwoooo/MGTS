"""Прозрачные правила для оценки обратной связи, локально и без передачи текста."""

import re

import pandas as pd

from . import surveys as dl
from .models import Chart, Signal

COMMENT_THEMES = {
    "Нагрузка и сроки": r"перегруз|слишком много|не успева|не хватw* времен|нарушw* срок|срывw* срок",
    "Вводные и приоритеты": r"неясн|непонятн|не понятн|не хватw* (?:вводн|инструкц)|неяснw* приоритет",
    "Доступы и инструменты": r"нет доступ|не хватw* доступ|долгw* оформленw* доступ|проблемw* с доступ",
    "Поддержка и обратная связь": r"не хватw* (?:поддержк|обратной связи)|редкw* обратнw* связ|сложно получw* обратн",
}


def evaluate_signals(charts: list[Chart], interns: pd.DataFrame, mentors: pd.DataFrame) -> list[Signal]:
    signals = []
    for chart in charts:
        series = chart.series[0]
        observed = [point for point in series.points if point.value is not None]
        label = f"{chart.label} · {series.label.lower()}"
        for threshold, level in [(2, "critical"), (3, "attention")]:
            low = [point.month for point in observed if (point.value <= 2 if threshold == 2 else 2 < point.value < 4)]
            if low:
                signals.append(Signal(
                    level=level, label=label,
                    detail="Оценка до 2 из 5." if threshold == 2 else "Оценка ниже 4 из 5.",
                    months=low, source="monthly",
                ))
        drops = [(before, after) for before, after in zip(observed, observed[1:]) if before.value - after.value >= 1]
        if drops:
            signals.append(Signal(
                level="attention", label=f"Снижение: {label}",
                detail="Снижение между доступными оценками на один балл и более.",
                months=[after.month for _, after in drops], source="monthly",
            ))

    points = {chart.id: {point.month: point.value for point in chart.series[0].points} for chart in charts}
    for own, mentor, label in [
        ("clarity", "expectations", "Понятность задач"),
        ("team", "collaboration", "Взаимодействие с командой"),
    ]:
        gaps = [
            month for month, left in points[own].items()
            if left is not None and points[mentor][month] is not None and abs(left - points[mentor][month]) >= 2
        ]
        if gaps:
            signals.append(Signal(
                level="attention", label=f"Расхождение по теме «{label}»",
                detail="Разница в два балла и более по близким вопросам двух источников.",
                months=gaps, source="monthly",
            ))

    for label, pattern in COMMENT_THEMES.items():
        matches = set()
        for data, fields in ((interns, dl.INTERN_NOTES), (mentors, dl.MENTOR_NOTES)):
            for _, row in data.iterrows():
                for field in fields:
                    if pd.notna(row[field]) and re.search(pattern, str(row[field]).lower().replace("ё", "е")):
                        matches.add(int(row[dl.MONTH]))
        if len(matches) >= 2:
            signals.append(Signal(
                level="attention", label=f"Повтор в комментариях: {label.lower()}",
                detail="Тема отмечена по текстовым признакам в нескольких анкетах. Проверьте формулировки в комментариях.",
                months=sorted(matches), source="feedback",
            ))
    return sorted(signals, key=lambda signal: signal.level != "critical")
