"""Загрузка и подготовка данных опросов для дашборда.

Данные читаются из Excel-файлов в папке ``data`` через модуль
``data.read_excel`` (``load_excel``), чтобы дашборд и остальной проект
использовали единый способ чтения таблиц.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

from data.read_excel import load_excel

DATA_DIR = ROOT / "data"
INTERN_FILE = DATA_DIR / "intern_survey.xlsx"
MENTOR_FILE = DATA_DIR / "mentor_survey.xlsx"

INTERN_ID = "ID стажёра"
MENTOR_ID = "ID наставника"
MONTH = "Месяц"
NPS = "NPS"
HIRE_READINESS = "Готовность к найму"
HOURS = "Затраченное время (ч)"
COMMENT = "Комментарий"

INTERN_METRICS = [
    "Удовлетворённость",
    "Нагрузка",
    "Ясность задач",
    "Поддержка наставника",
    "Прогресс в обучении",
    "Мотивация",
]
MENTOR_METRICS = [
    "Удовлетворённость",
    "Прогресс стажёра",
    "Качество материалов",
    "Поддержка компании",
]

INTERN_COLUMNS = [INTERN_ID, MONTH, *INTERN_METRICS, NPS, COMMENT]
MENTOR_COLUMNS = [
    MENTOR_ID,
    INTERN_ID,
    MONTH,
    *MENTOR_METRICS,
    HOURS,
    HIRE_READINESS,
    COMMENT,
]


def _load(path: Path, expected_columns: list[str]) -> pd.DataFrame:
    df = load_excel(path, sheet_name="Данные")
    missing = [col for col in expected_columns if col not in df.columns]
    if missing:
        raise ValueError(f"В файле {path.name} отсутствуют колонки: {missing}")
    df[MONTH] = df[MONTH].astype(int)
    return df.sort_values([df.columns[0], MONTH]).reset_index(drop=True)


def load_intern_data() -> pd.DataFrame:
    """Таблица ответов стажёров (5 стажёров × 6 месяцев)."""
    return _load(INTERN_FILE, INTERN_COLUMNS)


def load_mentor_data() -> pd.DataFrame:
    """Таблица ответов наставников (5 наставников × 6 месяцев)."""
    return _load(MENTOR_FILE, MENTOR_COLUMNS)


def load_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_intern_data(), load_mentor_data()


def intern_ids(intern_df: pd.DataFrame) -> list[str]:
    return sorted(intern_df[INTERN_ID].unique().tolist())


def mentor_ids(mentor_df: pd.DataFrame) -> list[str]:
    return sorted(mentor_df[MENTOR_ID].unique().tolist())


def overall_metrics(intern_df: pd.DataFrame, mentor_df: pd.DataFrame) -> dict[str, float]:
    """Ключевые показатели в целом по обеим таблицам."""
    return {
        "interns": int(intern_df[INTERN_ID].nunique()),
        "mentors": int(mentor_df[MENTOR_ID].nunique()),
        "months": int(intern_df[MONTH].nunique()),
        "responses": int(len(intern_df) + len(mentor_df)),
        "intern_satisfaction": round(float(intern_df["Удовлетворённость"].mean()), 2),
        "mentor_satisfaction": round(float(mentor_df["Удовлетворённость"].mean()), 2),
        "avg_nps": round(float(intern_df[NPS].mean()), 1),
        "avg_progress": round(float(mentor_df["Прогресс стажёра"].mean()), 2),
        "hire_readiness": round(float(mentor_df[HIRE_READINESS].mean()), 1),
        "mentor_hours": round(float(mentor_df[HOURS].sum()), 1),
    }


def monthly_mean(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Средние значения метрик по месяцам."""
    return df.groupby(MONTH, as_index=False)[columns].mean().sort_values(MONTH)


def intern_summary(intern_df: pd.DataFrame) -> pd.DataFrame:
    """Средние ответы каждого стажёра за все месяцы."""
    summary = (
        intern_df.groupby(INTERN_ID, as_index=False)[[*INTERN_METRICS, NPS]]
        .mean()
        .round(2)
        .sort_values(INTERN_ID)
        .reset_index(drop=True)
    )
    return summary


def intern_timeline(intern_df: pd.DataFrame, intern_id: str) -> pd.DataFrame:
    """Динамика ответов одного стажёра по месяцам."""
    return (
        intern_df[intern_df[INTERN_ID] == intern_id]
        .sort_values(MONTH)
        .reset_index(drop=True)
    )


def mentor_timeline(mentor_df: pd.DataFrame, intern_id: str) -> pd.DataFrame:
    """Динамика оценок наставника по конкретному стажёру."""
    return (
        mentor_df[mentor_df[INTERN_ID] == intern_id]
        .sort_values(MONTH)
        .reset_index(drop=True)
    )


def mentor_comments(mentor_df: pd.DataFrame, intern_id: str) -> pd.DataFrame:
    """Комментарии наставника по конкретному стажёру."""
    cols = [MENTOR_ID, MONTH, "Прогресс стажёра", HIRE_READINESS, COMMENT]
    return (
        mentor_df[mentor_df[INTERN_ID] == intern_id][cols]
        .sort_values(MONTH)
        .reset_index(drop=True)
    )


def radar_profile(intern_df: pd.DataFrame, intern_id: str) -> tuple[list[str], list[float], list[float]]:
    """Профиль компетенций стажёра: первый и последний месяц."""
    timeline = intern_timeline(intern_df, intern_id)
    first = timeline.iloc[0]
    last = timeline.iloc[-1]
    return (
        INTERN_METRICS,
        [float(first[m]) for m in INTERN_METRICS],
        [float(last[m]) for m in INTERN_METRICS],
    )


def team_radar(intern_df: pd.DataFrame) -> tuple[list[str], list[float]]:
    """Средний профиль компетенций по всем стажёрам."""
    means = intern_df[INTERN_METRICS].mean()
    return INTERN_METRICS, [float(means[m]) for m in INTERN_METRICS]


def latest_snapshot(intern_df: pd.DataFrame, intern_id: str) -> dict[str, float]:
    """Последние (самые свежие) значения метрик стажёра."""
    last = intern_timeline(intern_df, intern_id).iloc[-1]
    snapshot = {m: float(last[m]) for m in INTERN_METRICS}
    snapshot[NPS] = float(last[NPS])
    snapshot[MONTH] = int(last[MONTH])
    return snapshot
