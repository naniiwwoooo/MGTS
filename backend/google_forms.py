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
MENTOR_SPREADSHEET = "1FQ6aoRbP-ZMkTf80mxnMhV28TnbSBluBdcWkxV1idW4"
MENTOR_GID = "1575164264"


@dataclass(frozen=True)
class Sheet:
    spreadsheet: str
    tab: str = "Ответы на форму (1)"
    gid: str | None = None
    use_csv: bool = False


def configured_sheet(role: str, default_id: str, default_gid: str) -> Sheet | None:
    prefix = f"MGTS_GOOGLE_{role}"
    spreadsheet = os.getenv(f"{prefix}_SHEET_ID", default_id).strip()
    if not spreadsheet:
        return None
    tab = os.getenv(f"{prefix}_TAB")
    gid = os.getenv(f"{prefix}_GID")
    provided_sheet = spreadsheet == default_id
    if gid is None and tab is None and provided_sheet:
        gid = default_gid
    use_csv = bool(gid) and provided_sheet and os.getenv(f"{prefix}_PRIVATE") != "1"
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


def read_forms(sheet: Sheet, *, mentor: bool) -> tuple[pd.DataFrame, list[int]]:
    rows = fetch_rows(sheet)
    origin = "Google Forms · наставники" if mentor else "Google Forms · стажеры"
    if not rows:
        raise surveys.SurveyDataError(f"{origin}. В таблице нет строки заголовков.")
    headers, *answers = rows
    if any(len(row) > len(headers) for row in answers):
        raise surveys.SurveyDataError(f"{origin}. В ответах есть ячейки без заголовка.")
    frame = pd.DataFrame([row + [None] * (len(headers) - len(row)) for row in answers], columns=headers)
    if not mentor:
        frame = frame.rename(columns=lambda column: surveys.INTERN_ID if str(column).strip() == "ID" else column)
    rejected: set[int] = set()
    normalized = surveys.normalize(frame, origin, mentor=mentor, live=True, rejected_rows=rejected)
    normalized[surveys.INTERN_ID] = normalized[surveys.INTERN_ID].str.replace(
        r"(?i)^[сc][тt](?=-[0-9]+$)", "СТ", regex=True,
    )
    if mentor:
        normalized[surveys.MENTOR_ID] = normalized[surveys.MENTOR_ID].str.replace(
            r"(?i)^[нh](?=-[0-9]+$)", "Н", regex=True,
        )
    return normalized, sorted(rejected)


def match_departments(
    responses: pd.DataFrame, roster: dict[str, str], *, allow_new: bool,
) -> tuple[pd.DataFrame, list[int], list[int]]:
    accepted = responses.copy()
    rejected = []
    pending = []
    for index, intern_id, department in responses[[surveys.INTERN_ID, surveys.DEPARTMENT]].itertuples():
        expected = roster.setdefault(intern_id, department) if allow_new else roster.get(intern_id)
        if expected is None:
            pending.append(index)
        elif department_key(department) != department_key(expected):
            rejected.append(index)
        else:
            accepted.at[index, surveys.DEPARTMENT] = expected
    return accepted.drop(index=[*rejected, *pending]), rejected, pending


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
        self.responses: dict[bool, tuple[Sheet, pd.DataFrame, list[int]]] = {}

    def load(
        self, sheet: Sheet | None, empty: pd.DataFrame, *, mentor: bool,
    ) -> tuple[pd.DataFrame, list[int], str | None]:
        cached = self.responses.get(mentor)
        if cached and cached[0] != sheet:
            self.responses.pop(mentor)
            cached = None
        if sheet is None:
            return empty, [], None
        try:
            rows, rejected = read_forms(sheet, mentor=mentor)
            self.responses[mentor] = (sheet, rows, rejected)
            return rows, rejected, None
        except surveys.SurveyDataError as exc:
            detail = str(exc)
        except ImportError:
            detail = "Установите backend/requirements-google.txt."
        except requests.HTTPError as exc:
            denied = exc.response is not None and exc.response.status_code in (401, 403, 404)
            detail = "Проверьте доступ на чтение к вкладке Google Sheets." if denied else "Ошибка Google Sheets."
        except Exception:
            detail = (
                "Проверьте сеть и доступ к Google Sheets." if sheet.use_csv
                else "Проверьте доступ служебного аккаунта и настройки Google Sheets API."
            )
        rows, rejected = cached[1:] if cached else (empty, [])
        label = "Наставники" if mentor else "Стажёры"
        return rows, rejected, f"{label}: {detail}"

    def update(self, history: Snapshot) -> Snapshot:
        intern = configured_sheet("INTERN", INTERN_SPREADSHEET, INTERN_GID)
        mentor = configured_sheet("MENTOR", MENTOR_SPREADSHEET, MENTOR_GID)
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
            interns, bad_interns, intern_error = self.load(intern, history.interns.iloc[:0], mentor=False)
            mentors, bad_mentors, mentor_error = self.load(mentor, history.mentors.iloc[:0], mentor=True)
            roster = history.interns.set_index(surveys.INTERN_ID)[surveys.DEPARTMENT].to_dict()
            interns, wrong_interns, _ = match_departments(interns, roster, allow_new=True)
            mentors, wrong_mentors, pending = match_departments(mentors, roster, allow_new=False)
            current = merge(history, interns, mentors)
            errors = [error for error in (intern_error, mentor_error) if error]
            state = "connected" if not errors else "partial" if len(errors) < len(sources) else "error"
            details = errors.copy()
            for role, skipped in (("стажёров", bad_interns + wrong_interns), ("наставников", bad_mentors + wrong_mentors)):
                if skipped:
                    numbers = ", ".join(str(number + 2) for number in sorted(skipped)[:5])
                    details.append(f"Ответы {role} с ошибками пропущены ({len(skipped)}). Строки в Google Sheets: {numbers}.")
            if pending:
                details.append(f"Ответы наставников ожидают появления профиля стажёра ({len(pending)}).")
            self.next_check = monotonic() + INTERVAL_SECONDS
            self.last_snapshot = replace(current, sync=SyncStatus(
                state=state, checked_at=datetime.now(timezone.utc), detail=" ".join(details) or None, sources=sources,
            ))
            return self.last_snapshot
