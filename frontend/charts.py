"""Построение графиков Plotly в минималистичном стиле Apple."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from frontend import data_loader as dl

INK = "#1d1d1f"
MUTED = "#6e6e73"
GRID = "#ececf0"
LINE = "#d2d2d7"
ACCENT = "#0071e3"
PALETTE = ["#0071e3", "#34c759", "#ff9f0a", "#af52de", "#ff3b30", "#5ac8fa", "#ff2d55"]
FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Arial, sans-serif'


def _theme(fig: go.Figure, height: int = 340, show_legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=INK, size=13),
        margin=dict(l=8, r=8, t=36, b=8),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", font=dict(family=FONT, color=INK), bordercolor=LINE),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12, color=MUTED),
        ),
        showlegend=show_legend,
        colorway=PALETTE,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=LINE, tickcolor=LINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=LINE, tickcolor=LINE, tickfont=dict(color=MUTED))
    return fig


def satisfaction_trend(intern_df: pd.DataFrame, mentor_df: pd.DataFrame) -> go.Figure:
    intern = dl.monthly_mean(intern_df, ["Удовлетворённость"]).rename(columns={"Удовлетворённость": "Стажёры"})
    mentor = dl.monthly_mean(mentor_df, ["Удовлетворённость"]).rename(columns={"Удовлетворённость": "Наставники"})
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=intern[dl.MONTH], y=intern["Стажёры"], name="Стажёры", mode="lines+markers",
            line=dict(width=3, color=PALETTE[0], shape="linear"), marker=dict(size=8),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=mentor[dl.MONTH], y=mentor["Наставники"], name="Наставники", mode="lines+markers",
            line=dict(width=3, color=PALETTE[1], shape="linear"), marker=dict(size=8),
        )
    )
    fig.update_yaxes(range=[1, 5], dtick=1)
    fig.update_xaxes(dtick=1, title="Месяц")
    return _theme(fig)


def progress_trend(intern_df: pd.DataFrame, mentor_df: pd.DataFrame) -> go.Figure:
    self_progress = dl.monthly_mean(intern_df, ["Прогресс в обучении"]).rename(
        columns={"Прогресс в обучении": "Самооценка стажёра"}
    )
    mentor_view = dl.monthly_mean(mentor_df, ["Прогресс стажёра"]).rename(
        columns={"Прогресс стажёра": "Оценка наставника"}
    )
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=self_progress[dl.MONTH], y=self_progress["Самооценка стажёра"], name="Самооценка стажёра",
            mode="lines+markers", line=dict(width=3, color=PALETTE[3], shape="linear"), marker=dict(size=8),
            fill="tozeroy", fillcolor="rgba(175,82,222,0.08)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=mentor_view[dl.MONTH], y=mentor_view["Оценка наставника"], name="Оценка наставника",
            mode="lines+markers", line=dict(width=3, color=PALETTE[2], shape="linear"), marker=dict(size=8),
        )
    )
    fig.update_yaxes(range=[1, 5], dtick=1)
    fig.update_xaxes(dtick=1, title="Месяц")
    return _theme(fig)


def nps_trend(intern_df: pd.DataFrame) -> go.Figure:
    data = dl.monthly_mean(intern_df, [dl.NPS])
    fig = go.Figure(
        go.Bar(
            x=data[dl.MONTH], y=data[dl.NPS], marker_color=PALETTE[0],
            marker_line_width=0, width=0.5, name="Рекомендация",
        )
    )
    fig.update_yaxes(range=[0, 10], dtick=2)
    fig.update_xaxes(dtick=1, title="Месяц")
    return _theme(fig, show_legend=False)


def hire_readiness_trend(mentor_df: pd.DataFrame) -> go.Figure:
    data = dl.monthly_mean(mentor_df, [dl.HIRE_READINESS])
    fig = go.Figure(
        go.Scatter(
            x=data[dl.MONTH], y=data[dl.HIRE_READINESS], mode="lines+markers",
            line=dict(width=3, color=PALETTE[1], shape="linear"), marker=dict(size=8),
            fill="tozeroy", fillcolor="rgba(52,199,89,0.10)", name="Готовность к найму",
        )
    )
    fig.update_yaxes(range=[0, 10], dtick=2)
    fig.update_xaxes(dtick=1, title="Месяц")
    return _theme(fig, show_legend=False)


def mentor_hours(mentor_df: pd.DataFrame) -> go.Figure:
    data = mentor_df.groupby(dl.MONTH, as_index=False)[dl.HOURS].sum()
    fig = go.Figure(
        go.Bar(
            x=data[dl.MONTH], y=data[dl.HOURS], marker_color=PALETTE[3],
            marker_line_width=0, width=0.5, name="Часы",
        )
    )
    fig.update_xaxes(dtick=1, title="Месяц")
    fig.update_yaxes(title="Часы")
    return _theme(fig, show_legend=False)


def satisfaction_heatmap(intern_df: pd.DataFrame) -> go.Figure:
    pivot = intern_df.pivot(index=dl.INTERN_ID, columns=dl.MONTH, values="Удовлетворённость")
    fig = px.imshow(
        pivot,
        text_auto=True,
        aspect="auto",
        color_continuous_scale=["#eef4ff", "#cfe2ff", "#8ab8f7", ACCENT],
        zmin=1,
        zmax=5,
    )
    fig.update_coloraxes(showscale=False)
    fig.update_xaxes(title="Месяц", dtick=1)
    fig.update_yaxes(title=None)
    return _theme(fig, height=320, show_legend=False)


def nps_by_intern(intern_df: pd.DataFrame) -> go.Figure:
    summary = dl.intern_summary(intern_df).sort_values(dl.NPS)
    fig = go.Figure(
        go.Bar(
            x=summary[dl.NPS], y=summary[dl.INTERN_ID], orientation="h",
            marker_color=PALETTE[0], marker_line_width=0,
            text=summary[dl.NPS].round(1), textposition="outside",
        )
    )
    fig.update_xaxes(range=[0, 10], dtick=2)
    return _theme(fig, show_legend=False)


def team_radar(intern_df: pd.DataFrame) -> go.Figure:
    categories, values = dl.team_radar(intern_df)
    fig = go.Figure(
        go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            fillcolor="rgba(0,113,227,0.12)",
            line=dict(color=ACCENT, width=2),
            name="Средний профиль",
        )
    )
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, range=[0, 5], showticklabels=False, gridcolor=GRID, linecolor=LINE),
            angularaxis=dict(gridcolor=GRID, linecolor=LINE, tickfont=dict(size=11, color=MUTED)),
        )
    )
    return _theme(fig, height=360, show_legend=False)


def intern_timeline_chart(
    timeline: pd.DataFrame, metrics: list[str] | None = None,
) -> go.Figure:
    fig = go.Figure()
    for i, metric in enumerate(metrics if metrics is not None else dl.INTERN_METRICS):
        fig.add_trace(
            go.Scatter(
                x=timeline[dl.MONTH], y=timeline[metric], name=metric,
                mode="lines+markers",
                line=dict(width=2.5, color=PALETTE[i % len(PALETTE)], shape="linear"),
                marker=dict(size=7),
            )
        )
    fig.update_yaxes(range=[1, 5], dtick=1)
    fig.update_xaxes(dtick=1, title="Месяц")
    return _theme(fig, height=400)


def intern_nps_chart(timeline: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=timeline[dl.MONTH], y=timeline[dl.NPS], marker_color=PALETTE[0],
            marker_line_width=0, width=0.5, text=timeline[dl.NPS], textposition="outside",
        )
    )
    fig.update_yaxes(range=[0, 10], dtick=2)
    fig.update_xaxes(dtick=1, title="Месяц")
    return _theme(fig, height=300, show_legend=False)


def intern_radar(intern_df: pd.DataFrame, intern_id: str) -> go.Figure:
    categories, first, last = dl.radar_profile(intern_df, intern_id)
    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=first + [first[0]], theta=categories + [categories[0]],
            name="Первый месяц", line=dict(color=LINE, width=2),
            fill="toself", fillcolor="rgba(210,210,215,0.20)",
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=last + [last[0]], theta=categories + [categories[0]],
            name="Последний месяц", line=dict(color=ACCENT, width=2.5),
            fill="toself", fillcolor="rgba(0,113,227,0.15)",
        )
    )
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, range=[0, 5], showticklabels=False, gridcolor=GRID, linecolor=LINE),
            angularaxis=dict(gridcolor=GRID, linecolor=LINE, tickfont=dict(size=11, color=MUTED)),
        )
    )
    return _theme(fig, height=380)


def mentor_progress_trend(mentor_df: pd.DataFrame) -> go.Figure:
    data = dl.monthly_mean(mentor_df, ["Прогресс стажёра"])
    fig = go.Figure(go.Scatter(
        x=data[dl.MONTH], y=data["Прогресс стажёра"], mode="lines+markers",
        line=dict(width=3, color=ACCENT), marker=dict(size=8),
        name="Прогресс",
    ))
    fig.update_xaxes(dtick=1, title="Месяц")
    fig.update_yaxes(range=[1, 5], dtick=1)
    return _theme(fig, show_legend=False)


def intern_mentor_progress(mentor_timeline: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=mentor_timeline[dl.MONTH], y=mentor_timeline["Прогресс стажёра"], name="Прогресс стажёра",
            mode="lines+markers", line=dict(width=3, color=PALETTE[2], shape="linear"), marker=dict(size=8),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=mentor_timeline[dl.MONTH], y=mentor_timeline[dl.HIRE_READINESS], name="Готовность к найму",
            mode="lines+markers", line=dict(width=3, color=PALETTE[1], shape="linear", dash="dot"),
            marker=dict(size=8), yaxis="y2",
        )
    )
    fig.update_xaxes(dtick=1, title="Месяц")
    _theme(fig, height=360)
    fig.update_layout(
        yaxis=dict(range=[1, 5], dtick=1, title="Прогресс (1–5)"),
        yaxis2=dict(range=[0, 10], dtick=2, title="Готовность (0–10)", overlaying="y", side="right", showgrid=False),
    )
    return fig


PLOT_CONFIG = {"displayModeBar": False, "responsive": True}
