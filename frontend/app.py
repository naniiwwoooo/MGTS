"""Streamlit-дашборд стажёрской программы (стиль apple.com)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(Path(__file__).resolve().parent)):
    if path not in sys.path:
        sys.path.insert(0, path)

from frontend import charts  # noqa: E402
from frontend import data_loader as dl  # noqa: E402
import llm  # noqa: E402
from frontend import style  # noqa: E402

st.set_page_config(
    page_title="MGTS · Дашборд стажёрской программы",
    page_icon="🍏",
    layout="wide",
    initial_sidebar_state="collapsed",
)

style.inject_css()


@st.cache_data(show_spinner=False)
def get_data():
    return dl.load_all()


def show_chart(fig) -> None:
    st.plotly_chart(fig, width="stretch", config=charts.PLOT_CONFIG)


def render_overview(intern_df, mentor_df) -> None:
    m = dl.overall_metrics(intern_df, mentor_df)

    style.kpi_grid(
        [
            {"label": "Участники", "value": f"{m['interns']} + {m['mentors']}", "sub": "стажёры · наставники"},
            {"label": "Удовлетворённость", "value": f"{m['intern_satisfaction']:g}/5", "sub": f"наставники {m['mentor_satisfaction']:g}/5"},
            {"label": "NPS стажёров", "value": f"{m['avg_nps']:g}/10", "sub": "среднее за 6 месяцев"},
            {"label": "Готовность к найму", "value": f"{m['hire_readiness']:g}/10", "sub": "оценка наставников"},
            {"label": "Часы наставничества", "value": f"{m['mentor_hours']:g}", "sub": f"{m['responses']} ответов"},
        ]
    )

    style.section("Динамика по месяцам", "Как менялись ключевые показатели за полгода.")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("Удовлетворённость · 1–5")
        show_chart(charts.satisfaction_trend(intern_df, mentor_df))
    with c2:
        st.caption("Прогресс · 1–5")
        show_chart(charts.progress_trend(intern_df, mentor_df))
    with c3:
        st.caption("NPS стажёров · 0–10")
        show_chart(charts.nps_trend(intern_df))

    style.section("Сравнение стажёров", "Тепловая карта удовлетворённости и итоговый NPS.")
    c1, c2 = st.columns([1.7, 1])
    with c1:
        st.caption("Удовлетворённость по месяцам")
        show_chart(charts.satisfaction_heatmap(intern_df))
    with c2:
        st.caption("Средний NPS по стажёрам")
        show_chart(charts.nps_by_intern(intern_df))

    style.section("Наставники", "Нагрузка, готовность к найму и средний профиль команды.")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("Часы наставничества по месяцам")
        show_chart(charts.mentor_hours(mentor_df))
    with c2:
        st.caption("Готовность к найму · 0–10")
        show_chart(charts.hire_readiness_trend(mentor_df))
    with c3:
        st.caption("Средний профиль компетенций")
        show_chart(charts.team_radar(intern_df))

    impression = llm.generate_overall_impression(intern_df, mentor_df)
    if not llm.llm_available():
        impression += " Здесь появится развёрнутый анализ от LLM, когда подключим модель."
    style.ai_block("Общее впечатление от программы", impression)


def render_interns(intern_df, mentor_df) -> None:
    ids = dl.intern_ids(intern_df)
    selected = st.selectbox("Выберите стажёра", ids, label_visibility="collapsed")
    timeline = dl.intern_timeline(intern_df, selected)
    snapshot = dl.latest_snapshot(intern_df, selected)
    summary = dl.intern_summary(intern_df)
    row = summary[summary[dl.INTERN_ID] == selected].iloc[0]

    style.kpi_grid(
        [
            {"label": "Удовлетворённость", "value": f"{row['Удовлетворённость']:g}/5", "sub": "среднее за 6 месяцев"},
            {"label": "Прогресс в обучении", "value": f"{row['Прогресс в обучении']:g}/5", "sub": "самооценка"},
            {"label": "Мотивация", "value": f"{row['Мотивация']:g}/5", "sub": "среднее"},
            {"label": "NPS", "value": f"{snapshot[dl.NPS]:g}/10", "sub": f"последний месяц · {snapshot[dl.MONTH]}"},
        ]
    )

    with st.spinner("ИИ готовит общее мнение о стажёре…"):
        intern_impression = llm.generate_intern_impression(intern_df, mentor_df, selected)
    if not llm.llm_available():
        intern_impression += " Здесь появится развёрнутый анализ от LLM, когда подключим модель."
    style.ai_block(f"Общее мнение ИИ о стажёре {selected}", intern_impression, badge="ИИ")

    style.section("Динамика ответов за 6 месяцев", "Все метрики опроса стажёра по месяцам.")
    show_chart(charts.intern_timeline_chart(timeline))

    c1, c2 = st.columns([1, 1])
    with c1:
        st.caption("NPS по месяцам · 0–10")
        show_chart(charts.intern_nps_chart(timeline))
    with c2:
        st.caption("Профиль компетенций: первый и последний месяц")
        show_chart(charts.intern_radar(intern_df, selected))

    mentor_tl = dl.mentor_timeline(mentor_df, selected)
    comments = dl.mentor_comments(mentor_df, selected)

    style.section("Оценки и комментарии наставника", f"Обратная связь по стажёру {selected}.")
    if mentor_tl.empty:
        st.info("Для этого стажёра пока нет данных наставника.")
    else:
        c1, c2 = st.columns([1, 1.2])
        with c1:
            st.caption("Прогресс и готовность к найму")
            show_chart(charts.intern_mentor_progress(mentor_tl))
        with c2:
            st.caption("Комментарии по месяцам")
            left, right = st.columns(2)
            for i, (_, item) in enumerate(comments.iterrows()):
                target = left if i % 2 == 0 else right
                with target:
                    style.comment_card(
                        int(item[dl.MONTH]),
                        item[dl.MENTOR_ID],
                        item[dl.COMMENT],
                        float(item["Прогресс стажёра"]),
                        float(item[dl.HIRE_READINESS]),
                    )


def main() -> None:
    style.hero(
        "MGTS DASHBOARD",
        "Стажёрская программа",
        "Единый взгляд на прогресс стажёров и работу наставников за шесть месяцев",
    )

    try:
        intern_df, mentor_df = get_data()
    except FileNotFoundError as exc:
        st.error(f"Не найдены файлы данных: {exc}")
        st.stop()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Не удалось загрузить данные: {exc}")
        st.stop()

    tab_overview, tab_interns = st.tabs(["Общая картина", "По стажёрам"])
    with tab_overview:
        render_overview(intern_df, mentor_df)
    with tab_interns:
        render_interns(intern_df, mentor_df)


if __name__ == "__main__":
    main()
