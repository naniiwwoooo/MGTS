"""Чтение вкладок Google Sheets, связанных с Google Forms."""

import csv
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import os
from threading import Lock
from time import monotonic
from urllib.parse import quote

import pandas as pd
import requests

from . import surveys
from .dashboard import Snapshot
from .models import SyncStatus

SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
INTERVAL_SECONDS = 15
INTERN_SPREADSHEET = "1NYC30wiV42Tq459fBLIxOv1fyZJduEqltJARKC8kNM0"
INTERN_GID = "720609798"


@dataclass(frozen=True)
class Sheet:
    spreadsheet: str
    tab: str = "Ответы на форму (1)"
    gid: str | None = None
    use_csv: bool = False


def intern_sheet() -> Sheet | None:
    spreadsheet = os.getenv("MGTS_GOOGLE_INTERN_SHEET_ID", INTERN_SPREADSHEET).strip()
    if not spreadsheet:
        return None
    tab = os.getenv("MGTS_GOOGLE_INTERN_TAB")
    gid = os.getenv("MGTS_GOOGLE_INTERN_GID")
    provided_sheet = spreadsheet == INTERN_SPREADSHEET
    if gid is None and tab is None and provided_sheet:
        gid = INTERN_GID
    use_csv = bool(gid) and provided_sheet and os.getenv("MGTS_GOOGLE_INTERN_PRIVATE") != "1"
    return Sheet(spreadsheet, tab or "Ответы на форму (1)", gid, use_csv)


def fetch_rows(sheet: Sheet) -> list[list]:
    spreadsheet = quote(sheet.spreadsheet, safe="")
    if sheet.use_csv:
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet}/export"
        response = requests.get(url, params={"format": "csv", "gid": sheet.gid}, timeout=(4, 15))
        response.raise_for_status()
        if response.headers.get("Content-Type", "").split(";")[0] != "text/csv":
            raise surveys.SurveyDataError("Google не вернул CSV. Проверьте доступ к вкладке ответов.")
        return list(csv.reader(StringIO(response.content.decode("utf-8-sig"), newline="")))

    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=[SCOPE])
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet}"
    with AuthorizedSession(credentials, refresh_timeout=8) as session:
        title = sheet.tab
        if sheet.gid is not None:
            response = session.get(url, params={"fields": "sheets(properties(sheetId,title))"}, timeout=8)
            response.raise_for_status()
            title = next((
                item["properties"]["title"] for item in response.json().get("sheets", [])
                if str(item["properties"]["sheetId"]) == sheet.gid
            ), None)
            if title is None:
                raise surveys.SurveyDataError("В Google Sheets не найдена вкладка с указанным gid.")
        tab = "'" + title.replace("'", "''") + "'"
        response = session.get(f"{url}/values/{quote(tab, safe='')}", params={"valueRenderOption": "UNFORMATTED_VALUE"}, timeout=8)
        response.raise_for_status()
        return response.json().get("values", [])


def read_forms(
    sheet: Sheet, *, mentor: bool, roster: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[int]]:
    rows = fetch_rows(sheet)
    origin = "Google Forms · наставники" if mentor else "Google Forms · стажеры"
    if not rows:
        raise surveys.SurveyDataError(f"{origin}. В таблице нет строки заголовков.")
    headers, *answers = rows
    if any(len(row) > len(headers) for row in answers):
        raise surveys.SurveyDataError(f"{origin}. В ответах есть ячейки без заголовка.")
    frame = pd.DataFrame([row + [None] * (len(headers) - len(row)) for row in answers], columns=headers)
    if mentor:
        return surveys.normalize(frame, origin, mentor=True, live=True), []

    frame = frame.rename(columns=lambda column: surveys.INTERN_ID if str(column).strip() == "ID" else column)
    rejected: set[int] = set()
    normalized = surveys.normalize(frame, origin, mentor=False, live=True, rejected_rows=rejected)
    normalized[surveys.INTERN_ID] = normalized[surveys.INTERN_ID].str.replace(
        r"(?i)^[сc][тt](?=-[0-9]+$)", "СТ", regex=True,
    )
    departments = dict(roster or {})
    for index, intern_id, department in normalized[[surveys.INTERN_ID, surveys.DEPARTMENT]].itertuples():
        expected = departments.setdefault(intern_id, department)
        if department_key(department) != department_key(expected):
            rejected.add(index)
        else:
            normalized.at[index, surveys.DEPARTMENT] = expected
    accepted = normalized.loc[~normalized.index.isin(rejected)]
    return accepted, sorted(index + 2 for index in rejected)


def department_key(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def merge(history: Snapshot, interns: pd.DataFrame, mentors: pd.DataFrame) -> Snapshot:
    def combine(old: pd.DataFrame, new: pd.DataFrame, *, mentor: bool) -> pd.DataFrame:
        if new.empty:
            return old
        keys = surveys.record_keys(mentor)
        return pd.concat([old, new], ignore_index=True).drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)

    combined_interns = combine(history.interns, interns, mentor=False)
    combined_mentors = combine(history.mentors, mentors, mentor=True)
    surveys.validate_roster(combined_interns, combined_mentors)
    if combined_interns.equals(history.interns) and combined_mentors.equals(history.mentors):
        return history
    new_ids = interns.loc[~interns[surveys.INTERN_ID].isin(history.interns[surveys.INTERN_ID]), surveys.INTERN_ID]
    newest_first = tuple(reversed(new_ids.unique()))
    content = combined_interns.to_json(force_ascii=False) + combined_mentors.to_json(force_ascii=False)
    version = (*history.version, sha256(content.encode()).hexdigest(), newest_first)
    return Snapshot(version, combined_interns, combined_mentors, new_intern_ids=newest_first)


class FormsSync:
    def __init__(self) -> None:
        self.lock = Lock()
        self.next_check = 0.0
        self.last_snapshot: Snapshot | None = None
        self.config: tuple | None = None

    def update(self, history: Snapshot) -> Snapshot:
        intern = intern_sheet()
        mentor_id = os.getenv("MGTS_GOOGLE_MENTOR_SHEET_ID", "").strip()
        mentor = Sheet(mentor_id, os.getenv("MGTS_GOOGLE_MENTOR_TAB", "Ответы на форму (1)")) if mentor_id else None
        if intern is None and mentor is None:
            return history
        sources = [role for role, sheet in (("interns", intern), ("mentors", mentor)) if sheet is not None]
        config = (history.version, intern, mentor)
        with self.lock:
            if config != self.config:
                self.config = config
                self.last_snapshot = history
                self.next_check = 0
            if monotonic() < self.next_check:
                return self.last_snapshot
            detail = None
            try:
                roster = history.interns.set_index(surveys.INTERN_ID)[surveys.DEPARTMENT].to_dict()
                interns, skipped = read_forms(intern, mentor=False, roster=roster) if intern else (history.interns.iloc[:0], [])
                mentors = read_forms(mentor, mentor=True)[0] if mentor else history.mentors.iloc[:0]
                current = merge(history, interns, mentors)
                state = "connected"
                if skipped:
                    numbers = ", ".join(str(number) for number in skipped[:5])
                    detail = f"Ответы стажёров с ошибками пропущены ({len(skipped)}). Строки в Google Sheets: {numbers}."
            except (surveys.SurveyDataError, ImportError) as exc:
                current = self.last_snapshot
                state = "error"
                detail = str(exc) if isinstance(exc, surveys.SurveyDataError) else "Установите backend/requirements-google.txt."
            except Exception:
                current = self.last_snapshot
                state = "error"
                detail = (
                    "Проверьте сеть и доступ к Google Sheets."
                    if intern and intern.use_csv and mentor is None
                    else "Проверьте доступ служебного аккаунта, настройки вкладок и состояние Sheets API."
                )
            self.next_check = monotonic() + INTERVAL_SECONDS
            self.last_snapshot = replace(current, sync=SyncStatus(
                state=state, checked_at=datetime.now(timezone.utc), detail=detail, sources=sources,
            ))
            return self.last_snapshot
