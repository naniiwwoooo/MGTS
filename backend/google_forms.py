"""Чтение двух закрытых таблиц, связанных с Google Forms."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import os
from threading import Lock
from time import monotonic
from urllib.parse import quote

import pandas as pd

from . import surveys
from .dashboard import Snapshot
from .models import SyncStatus

SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
INTERVAL_SECONDS = 60


@dataclass(frozen=True)
class Sheet:
    spreadsheet: str
    tab: str


def fetch_rows(sheet: Sheet) -> list[list]:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=[SCOPE])
    tab = "'" + sheet.tab.replace("'", "''") + "'"
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(sheet.spreadsheet, safe='')}/values/{quote(tab, safe='')}"
    with AuthorizedSession(credentials, refresh_timeout=8) as session:
        response = session.get(url, params={"valueRenderOption": "UNFORMATTED_VALUE"}, timeout=8)
        response.raise_for_status()
        return response.json().get("values", [])


def read_forms(sheet: Sheet, *, mentor: bool) -> pd.DataFrame:
    rows = fetch_rows(sheet)
    origin = "Google Forms · наставники" if mentor else "Google Forms · стажеры"
    if not rows:
        raise surveys.SurveyDataError(f"{origin}. В таблице нет строки заголовков.")
    headers, *answers = rows
    if any(len(row) > len(headers) for row in answers):
        raise surveys.SurveyDataError(f"{origin}. В ответах есть ячейки без заголовка.")
    frame = pd.DataFrame([row + [None] * (len(headers) - len(row)) for row in answers], columns=headers)
    return surveys.normalize(frame, origin, mentor=mentor, live=True)


def merge(history: Snapshot, interns: pd.DataFrame, mentors: pd.DataFrame) -> Snapshot:
    roster = history.interns.set_index(surveys.INTERN_ID)[surveys.DEPARTMENT].to_dict()
    for incoming in (interns, mentors):
        expected = incoming[surveys.INTERN_ID].map(roster)
        if expected.isna().any() or expected.ne(incoming[surveys.DEPARTMENT]).any():
            raise surveys.SurveyDataError("Ответы формы содержат неизвестный ID стажера или другое подразделение.")

    def combine(old: pd.DataFrame, new: pd.DataFrame, *, mentor: bool) -> pd.DataFrame:
        keys = surveys.record_keys(mentor)
        return pd.concat([old, new], ignore_index=True).drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)

    combined_interns = combine(history.interns, interns, mentor=False)
    combined_mentors = combine(history.mentors, mentors, mentor=True)
    surveys.validate_roster(combined_interns, combined_mentors)
    content = combined_interns.to_json(force_ascii=False) + combined_mentors.to_json(force_ascii=False)
    return Snapshot((*history.version, sha256(content.encode()).hexdigest()), combined_interns, combined_mentors)


class FormsSync:
    def __init__(self) -> None:
        self.lock = Lock()
        self.next_check = 0.0
        self.last_snapshot: Snapshot | None = None
        self.config: tuple | None = None

    def update(self, history: Snapshot) -> Snapshot:
        intern_id = os.getenv("MGTS_GOOGLE_INTERN_SHEET_ID", "").strip()
        mentor_id = os.getenv("MGTS_GOOGLE_MENTOR_SHEET_ID", "").strip()
        if not intern_id and not mentor_id:
            return history
        intern = Sheet(intern_id, os.getenv("MGTS_GOOGLE_INTERN_TAB", "Ответы на форму (1)"))
        mentor = Sheet(mentor_id, os.getenv("MGTS_GOOGLE_MENTOR_TAB", "Ответы на форму (1)"))
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
                if not intern.spreadsheet or not mentor.spreadsheet:
                    raise surveys.SurveyDataError("Укажите идентификаторы обеих таблиц Google Forms.")
                current = merge(history, read_forms(intern, mentor=False), read_forms(mentor, mentor=True))
                state = "connected"
            except (surveys.SurveyDataError, ImportError) as exc:
                current = self.last_snapshot
                state = "error"
                detail = str(exc) if isinstance(exc, surveys.SurveyDataError) else "Установите backend/requirements-google.txt."
            except Exception:
                current = self.last_snapshot
                state = "error"
                detail = "Проверьте доступ служебного аккаунта, названия вкладок и состояние Sheets API."
            self.next_check = monotonic() + INTERVAL_SECONDS
            self.last_snapshot = replace(current, sync=SyncStatus(state=state, checked_at=datetime.now(timezone.utc), detail=detail))
            return self.last_snapshot
