"""Резервный интерфейс Streamlit с общей моделью данных."""

from functools import partial
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if sys.path[0] != str(ROOT):
    sys.path.insert(0, str(ROOT))

from backend.dashboard import current_version, overview, profile, read_snapshot
from frontend.charts import survey_chart
import llm

OVERVIEW = "Обзор программы"
st.set_page_config(page_title="МГТС · Стажерская программа", layout="wide")


def main() -> None:
    try:
        snapshot = read_snapshot(current_version())
    except (OSError, ValueError):
        st.error("Не удалось загрузить данные. Проверьте файлы interns.xlsx и mentors.xlsx.")
        return

    program = overview(snapshot)
    selected = st.radio(
        "Раздел", [OVERVIEW, *(item.id for item in program.interns)],
        horizontal=True, key="dashboard_view",
    )
    selected_profile = profile(snapshot, selected) if selected != OVERVIEW else None
    data = selected_profile or program
    st.title(f"Стажёр {selected}" if selected_profile else OVERVIEW)
    for layout, metric in zip(st.columns(len(data.metrics)), data.metrics, strict=True):
        latest = metric.change.latest if metric.change else None
        value = f"{latest.value:g} / 5" if latest else "—"
        layout.metric(metric.label, value, help=metric.source)
    if selected_profile:
        st.caption(selected_profile.department)
        st.subheader("Анкеты и сигналы")
        st.dataframe([item.model_dump() for item in selected_profile.coverage])
        for item in selected_profile.signals:
            st.text(f"{item.label}. {item.detail}")
        st.subheader("Комментарии")
        for comment in [*selected_profile.comments, *selected_profile.intern_comments]:
            st.text(f"Месяц {comment.month} · {comment.author} · {comment.question}\n{comment.text}")
    else:
        st.dataframe([
            {"Стажёр": item.id, "Подразделение": item.department,
             "Анкеты стажёра": sum(p.intern_submitted for p in item.coverage),
             "Анкеты наставника": sum(p.mentor_submitted for p in item.coverage)}
            for item in program.interns
        ])
    for chart in (item for item in data.charts if item.id in ("clarity", "expectations", "development", "quality")):
        st.plotly_chart(survey_chart(chart), width="stretch")
    if llm.llm_available():
        key = f"analysis:{snapshot.data_version}:{selected}"
        if st.button("Сформировать вывод", key="generate_analysis"):
            generate = partial(llm.generate_overall_impression, snapshot.interns, snapshot.mentors)
            if selected_profile:
                generate = partial(llm.generate_intern_impression, snapshot.interns, snapshot.mentors, selected)
            st.session_state[key] = generate()
        if key in st.session_state:
            st.text(st.session_state[key])


if __name__ == "__main__":
    main()
