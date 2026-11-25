"""Дашборд для обзора стажёрской программы и работы с профилями."""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if sys.path[0] != str(ROOT):
    sys.path.insert(0, str(ROOT))

from frontend import charts, style  # noqa: E402
from frontend import data_loader as dl  # noqa: E402
import llm  # noqa: E402

OVERVIEW = "Обзор программы"

st.set_page_config(
    page_title="МГТС · Стажёрская программа",
    layout="wide",
    initial_sidebar_state="collapsed",
)

style.inject_css()


@st.cache_data(show_spinner=False)
def get_data():
    return dl.load_all()


def show_chart(title, fig) -> None:
    with st.container(border=True):
        st.markdown(f"##### {title}")
        st.plotly_chart(fig, width="stretch", config=charts.PLOT_CONFIG)


def score(value, scale: int) -> str:
    return f"{value:g}".replace(".", ",") + f" / {scale}"


def render_analysis(view: str, description: str, generate) -> None:
    if not llm.llm_available():
        return

    with st.expander("ИИ-анализ"):
        st.caption(description)
        if st.button("Сформировать вывод", key="generate_analysis"):
            with st.spinner("Формируем вывод по данным опросов…"):
                st.session_state[f"analysis:{view}"] = generate()
        if (result := st.session_state.get(f"analysis:{view}")):
            st.text(result)


def render_overview(intern_df, mentor_df) -> None:
    m = dl.overall_metrics(intern_df, mentor_df)
    style.heading(
        "Обзор программы",
        f"{m['interns']} стажёров · {m['mentors']} наставников · "
        f"{m['months']} месяцев · {m['responses']} ответов",
    )
    style.kpi_grid([
        {"label": "Удовлетворённость", "value": score(m["intern_satisfaction"], 5), "sub": "Среднее по стажёрам"},
        {"label": "Прогресс", "value": score(m["avg_progress"], 5), "sub": "Средняя оценка наставников"},
        {"label": "Готовность к найму", "value": score(m["hire_readiness"], 10), "sub": "Средняя оценка наставников"},
        {"label": "Часы наставничества", "value": f"{m['mentor_hours']:g} ч", "sub": "Всего за программу"},
    ])

    style.section("Динамика программы")
    left, right = st.columns(2)
    with left:
        show_chart("Удовлетворённость · 1–5", charts.satisfaction_trend(intern_df, mentor_df))
    with right:
        show_chart("Готовность к найму · 0–10", charts.hire_readiness_trend(mentor_df))

    with st.expander("Сравнение стажёров"):
        show_chart("Удовлетворённость по месяцам · 1–5", charts.satisfaction_heatmap(intern_df))
        show_chart("Средняя оценка готовности рекомендовать программу · 0–10", charts.nps_by_intern(intern_df))

    with st.expander("Прогресс, рекомендации и работа наставников"):
        show_chart("Прогресс в обучении · 1–5", charts.progress_trend(intern_df, mentor_df))
        show_chart(
            f"Готовность рекомендовать программу · {score(m['avg_nps'], 10)} в среднем",
            charts.nps_trend(intern_df),
        )
        show_chart("Часы наставничества по месяцам", charts.mentor_hours(mentor_df))
        show_chart("Средний профиль ответов стажёров", charts.team_radar(intern_df))

    render_analysis(
        OVERVIEW,
        "В запрос войдут сводные показатели программы.",
        partial(llm.generate_overall_impression, intern_df, mentor_df),
    )


def render_comment(item) -> None:
    style.comment_card(
        int(item[dl.MONTH]), item[dl.MENTOR_ID], item[dl.COMMENT],
        float(item["Прогресс стажёра"]), float(item[dl.HIRE_READINESS]),
    )


def render_intern(intern_df, mentor_df, selected: str) -> None:
    timeline = dl.intern_timeline(intern_df, selected)
    snapshot = dl.latest_snapshot(intern_df, selected)
    mentor_timeline = dl.mentor_timeline(mentor_df, selected)
    comments = dl.mentor_comments(mentor_df, selected)
    has_comment = comments[dl.COMMENT].fillna("").astype(str).str.strip().ne("")
    comments = comments.loc[has_comment].sort_values(dl.MONTH, ascending=False)
    month = int(snapshot[dl.MONTH])

    style.heading(
        f"Стажёр {selected}",
        f"Последний опрос — месяц {month}. Собрано ответов стажёра за {timeline[dl.MONTH].nunique()} мес.",
    )
    cards = [
        {"label": "Удовлетворённость", "value": score(snapshot["Удовлетворённость"], 5), "sub": "Ответ стажёра"},
        {"label": "Прогресс в обучении", "value": score(snapshot["Прогресс в обучении"], 5), "sub": "Самооценка стажёра"},
        {"label": "Мотивация", "value": score(snapshot["Мотивация"], 5), "sub": "Ответ стажёра"},
    ]
    if not mentor_timeline.empty:
        latest = mentor_timeline.iloc[-1]
        cards.append({
            "label": "Готовность к найму",
            "value": score(latest[dl.HIRE_READINESS], 10),
            "sub": f"Оценка наставника · месяц {int(latest[dl.MONTH])}",
        })
    style.kpi_grid(cards)

    style.section("Последний отзыв наставника")
    if comments.empty:
        st.caption("Комментариев наставников пока нет.")
    else:
        latest_month = comments[dl.MONTH].iloc[0]
        for _, item in comments[comments[dl.MONTH] == latest_month].iterrows():
            render_comment(item)
        earlier = comments[comments[dl.MONTH] < latest_month]
        if not earlier.empty:
            with st.expander("Предыдущие отзывы"):
                for _, item in earlier.iterrows():
                    render_comment(item)

    style.section("Динамика по месяцам")
    show_chart(
        "Удовлетворённость, прогресс и мотивация · 1–5",
        charts.intern_timeline_chart(timeline, ["Удовлетворённость", "Прогресс в обучении", "Мотивация"]),
    )

    if not mentor_timeline.empty:
        with st.expander("Динамика оценок наставника"):
            left, right = st.columns(2)
            with left:
                show_chart("Прогресс по оценке наставника · 1–5", charts.mentor_progress_trend(mentor_timeline))
            with right:
                show_chart("Готовность к найму · 0–10", charts.hire_readiness_trend(mentor_timeline))

    with st.expander("Все ответы стажёра"):
        show_chart("Показатели опроса · 1–5", charts.intern_timeline_chart(timeline))
        show_chart("Готовность рекомендовать программу · 0–10", charts.intern_nps_chart(timeline))
        show_chart("Ответы в первом и последнем месяце", charts.intern_radar(intern_df, selected))

    render_analysis(
        selected,
        f"В запрос по {selected} войдут ответы стажёра, оценки и комментарии наставников.",
        partial(llm.generate_intern_impression, intern_df, mentor_df, selected),
    )


def main() -> None:
    try:
        intern_df, mentor_df = get_data()
    except (OSError, ValueError):
        st.error("Не удалось загрузить опросы. Проверьте Excel-файлы в папке data и их листы «Данные».")
        st.stop()

    with st.container(key="dashboard_navigation"):
        st.markdown("**МГТС · Стажёрская программа**")
        selected = st.radio(
            "Выберите раздел дашборда",
            [OVERVIEW, *dl.intern_ids(intern_df)],
            format_func=lambda item: item if item == OVERVIEW else f"Стажёр {item}",
            horizontal=True,
            label_visibility="collapsed",
            key="dashboard_view",
        )

    if selected == OVERVIEW:
        render_overview(intern_df, mentor_df)
    else:
        render_intern(intern_df, mentor_df, selected)


if __name__ == "__main__":
    main()
