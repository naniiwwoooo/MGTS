"""Общая схема для исторических книг и таблиц ответов Google Forms."""

from pathlib import Path

import pandas as pd

from data.read_excel import load_excel

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INTERN_FILE = DATA_DIR / "interns.xlsx"
MENTOR_FILE = DATA_DIR / "mentors.xlsx"
INTERN_SHEET = "Ответы стажеров"
MENTOR_SHEET = "Оценки наставников"

INTERN_ID = "ID стажера"
MENTOR_ID = "ID наставника"
MONTH = "Контрольный период"
DEPARTMENT = "Подразделение / направление стажировки"

CLARITY = "Понятность задач"
SATISFACTION = "Общая удовлетворенность стажировкой"
DEVELOPMENT = "Профессиональное развитие"
EXPECTATIONS = "Понимание задач и ожиданий"
QUALITY = "Качество выполнения задач"
INTERN_METRICS = [
    CLARITY, "Поддержка и обратная связь наставника", "Комфортность нагрузки",
    "Интерес к задачам", DEVELOPMENT, "Взаимодействие с командой", SATISFACTION,
]
MENTOR_METRICS = [
    EXPECTATIONS, QUALITY, "Самостоятельность", "Соблюдение сроков и организация работы",
    "Вовлеченность и инициативность", "Взаимодействие с наставником и командой",
]
INTERN_NOTES = ["Сложности за период", "Что мешает работать и развиваться"]
MENTOR_NOTES = ["Комментарий о работе за период", "Сложности / ситуации для внимания"]
INTERN_COLUMNS = [INTERN_ID, DEPARTMENT, MONTH, *INTERN_METRICS, *INTERN_NOTES]
MENTOR_COLUMNS = [MENTOR_ID, INTERN_ID, DEPARTMENT, MONTH, *MENTOR_METRICS, *MENTOR_NOTES]


class SurveyDataError(ValueError):
    """Ошибку можно показать пользователю без содержимого строки."""


def normalize(data: pd.DataFrame, origin: str, *, mentor: bool, live: bool = False) -> pd.DataFrame:
    columns = MENTOR_COLUMNS if mentor else INTERN_COLUMNS
    fields = [INTERN_ID, DEPARTMENT, *([MENTOR_ID] if mentor else [])]
    metrics = MENTOR_METRICS if mentor else INTERN_METRICS
    entries = data.rename(columns=lambda name: " ".join(str(name).strip().split()).replace("ё", "е"))
    absent = [column for column in columns if column not in entries]
    if absent:
        raise SurveyDataError(f"{origin}. Отсутствуют колонки: {', '.join(absent)}.")
    if entries.columns.duplicated().any():
        raise SurveyDataError(f"{origin}. Найдены повторяющиеся заголовки.")
    entries = entries.loc[:, columns].copy().replace(r"^\s*$", pd.NA, regex=True).dropna(how="all")

    def invalid(mask: pd.Series, message: str) -> None:
        if mask.any():
            raise SurveyDataError(f"{origin}, строка {mask[mask].index[0] + 2}. {message}")

    for field in fields:
        entries[field] = entries[field].astype("string").str.strip()
        invalid(entries[field].isna(), f"Заполните колонку «{field}».")
    invalid(~entries[INTERN_ID].str.fullmatch(r"[\w-]+"), "ID стажера должен состоять из букв, цифр, дефиса или подчёркивания.")
    raw_month = entries[MONTH].astype("string").str.strip().str.replace(r"(?i)^месяц\s+", "", regex=True)
    months = pd.to_numeric(raw_month, errors="coerce")
    invalid(~months.isin(range(1, 7)), "Укажите контрольный месяц от 1 до 6.")
    entries[MONTH] = months.astype(int)
    for field in metrics:
        values = pd.to_numeric(entries[field], errors="coerce")
        invalid(entries[field].notna() & ~values.isin(range(1, 6)), f"«{field}» допускает целые оценки от 1 до 5.")
        entries[field] = values.astype(float)
    keys = record_keys(mentor)
    if live:
        entries = entries.drop_duplicates(keys, keep="last")
    else:
        invalid(entries.duplicated(keys), "Повторная анкета за один контрольный период.")
    return entries.sort_values(keys).reset_index(drop=True)


def record_keys(mentor: bool) -> list[str]:
    return [INTERN_ID, MONTH, *([MENTOR_ID] if mentor else [])]


def load_workbook(path: Path, sheet: str, *, mentor: bool) -> pd.DataFrame:
    try:
        frame = load_excel(path, sheet_name=sheet)
    except (OSError, ValueError) as exc:
        raise SurveyDataError(f"{path.name}. Проверьте наличие файла и листа «{sheet}».") from exc
    return normalize(frame, path.name, mentor=mentor)


def load_intern_data() -> pd.DataFrame:
    return load_workbook(INTERN_FILE, INTERN_SHEET, mentor=False)


def load_mentor_data() -> pd.DataFrame:
    return load_workbook(MENTOR_FILE, MENTOR_SHEET, mentor=True)


def validate_roster(interns: pd.DataFrame, mentors: pd.DataFrame) -> None:
    if interns.empty:
        raise SurveyDataError("В истории должна быть хотя бы одна анкета стажера.")
    combined = pd.concat([interns[[INTERN_ID, DEPARTMENT]], mentors[[INTERN_ID, DEPARTMENT]]])
    if not mentors[INTERN_ID].isin(interns[INTERN_ID]).all():
        raise SurveyDataError("В оценках наставников найден ID, которого нет в истории стажеров.")
    if combined.groupby(INTERN_ID)[DEPARTMENT].nunique().gt(1).any():
        raise SurveyDataError("В анкетах одного стажера указаны разные подразделения.")


def load_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    interns, mentors = load_intern_data(), load_mentor_data()
    validate_roster(interns, mentors)
    return interns, mentors


def intern_ids(data: pd.DataFrame) -> list[str]:
    return sorted(data[INTERN_ID].unique().tolist())


def mentor_ids(data: pd.DataFrame) -> list[str]:
    return sorted(data[MENTOR_ID].unique().tolist())


def intern_timeline(data: pd.DataFrame, intern_id: str) -> pd.DataFrame:
    return data.loc[data[INTERN_ID] == intern_id].sort_values(MONTH, kind="stable")


def mentor_timeline(data: pd.DataFrame, intern_id: str) -> pd.DataFrame:
    return intern_timeline(data, intern_id)


def monthly_mean(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return data.groupby(MONTH, as_index=False)[columns].mean()


def overall_metrics(interns: pd.DataFrame, mentors: pd.DataFrame) -> dict:
    return {
        "interns": len(intern_ids(interns)), "mentors": len(mentor_ids(mentors)),
        "months": interns[MONTH].nunique(), "responses": len(interns) + len(mentors),
        "intern_satisfaction": interns[SATISFACTION].mean(),
    }
