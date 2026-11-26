"""Адаптер Plotly для резервного интерфейса Streamlit."""

import plotly.graph_objects as go

from backend.models import Chart


def survey_chart(chart: Chart) -> go.Figure:
    figure = go.Figure()
    for source in chart.series:
        figure.add_scatter(
            x=[point.month for point in source.points],
            y=[point.value for point in source.points],
            mode="lines+markers",
            name=source.label,
            connectgaps=False,
        )
    figure.update_layout(
        title=chart.label, xaxis=dict(title="Контрольный месяц", dtick=1),
        yaxis=dict(title="Оценка", range=[.8, 5.2], dtick=1),
        margin=dict(l=14, r=14, t=50, b=35),
    )
    return figure
