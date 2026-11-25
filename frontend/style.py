"""Оформление дашборда в стиле apple.com: CSS и HTML-компоненты."""

from __future__ import annotations

from html import escape

import streamlit as st

CSS = """
<style>
:root {
    --apple-blue: #0071e3;
    --ink: #1d1d1f;
    --muted: #6e6e73;
    --bg: #ffffff;
    --surface: #f5f5f7;
    --surface-2: #fbfbfd;
    --line: #d2d2d7;
}

html, body, .stApp, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
                 "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}

.stApp { background: var(--bg); color: var(--ink); }

header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

.block-container {
    padding-top: 2.2rem;
    padding-bottom: 4rem;
    max-width: 1180px;
}

/* Navigation and headings */
.st-key-dashboard_navigation {
    margin-bottom: 0.75rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid #e8e8ed;
}
.st-key-dashboard_navigation [role="radiogroup"] {
    flex-wrap: wrap;
    gap: 0.4rem;
}
.st-key-dashboard_navigation [role="radiogroup"] label {
    min-height: 44px;
    margin: 0;
    padding: 0.35rem 0.85rem;
    border-radius: 999px;
    background: var(--surface);
}
.st-key-dashboard_navigation label:has(input:checked) {
    background: #e9f2ff;
    box-shadow: inset 0 0 0 1px #accfff;
}
.st-key-dashboard_navigation label:focus-within {
    outline: 2px solid var(--apple-blue);
    outline-offset: 2px;
}
.page-heading {
    padding: clamp(1.2rem, 4vw, 2.5rem);
    border-radius: 24px;
    background: linear-gradient(120deg, #f5f5f7, #edf4ff);
}
.page-heading h1 {
    padding: 0;
    margin: 0 0 0.45rem;
    font-size: clamp(2rem, 5vw, 3.5rem);
    font-weight: 700;
    letter-spacing: -0.045em;
    line-height: 1.06;
}
.page-heading p { color: var(--muted); margin: 0; }
.section {
    font-size: clamp(1.35rem, 3vw, 1.75rem);
    font-weight: 700;
    letter-spacing: -0.025em;
    margin: 0.8rem 0 0;
    padding: 0;
}
[data-testid="stExpander"] summary { min-height: 44px; font-weight: 600; }
[data-testid="stText"] { font-family: inherit; white-space: pre-wrap; overflow-wrap: anywhere; }

/* KPI cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
    gap: 16px;
    margin: 0.4rem 0 0.2rem;
}
.kpi-card {
    background: var(--surface);
    border-radius: 22px;
    padding: 22px 24px;
}
.kpi-label { color: var(--muted); font-size: 0.84rem; font-weight: 500; }
.kpi-value {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    margin-top: 0.35rem;
    line-height: 1;
}
.kpi-sub { color: var(--muted); font-size: 0.78rem; margin-top: 0.45rem; }

/* Comment cards */
.comment-card {
    background: var(--surface);
    border-radius: 20px;
    padding: 20px 22px;
    margin-bottom: 14px;
}
.comment-head {
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    margin-bottom: 0.55rem;
}
.comment-month { font-weight: 600; font-size: 0.98rem; }
.comment-meta { color: var(--muted); font-size: 0.8rem; }
.comment-text { font-size: 1.02rem; line-height: 1.55; color: var(--ink); }
.pill {
    display: inline-block;
    background: rgba(0, 113, 227, 0.1);
    color: var(--apple-blue);
    border-radius: 999px;
    padding: 3px 11px;
    font-size: 0.74rem;
    font-weight: 600;
    white-space: nowrap;
}
.pill-green { background: rgba(52, 199, 89, 0.14); color: #248a3d; }

@media (max-width: 580px) {
    .block-container { padding-inline: 1rem; }
    .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .kpi-card { padding: 14px 12px; border-radius: 16px; }
    .kpi-value { font-size: 1.5rem; }
    .comment-card { padding: 16px; }
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def heading(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="page-heading"><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    st.markdown(f'<h2 class="section">{escape(title)}</h2>', unsafe_allow_html=True)


def kpi_grid(cards: list[dict[str, str]]) -> None:
    """cards: список словарей с ключами label, value, sub (sub опционален)."""
    items = []
    for card in cards:
        sub = f'<div class="kpi-sub">{escape(card["sub"])}</div>' if card.get("sub") else ""
        items.append(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{escape(card["label"])}</div>'
            f'<div class="kpi-value">{escape(card["value"])}</div>'
            f'{sub}</div>'
        )
    st.markdown(f'<div class="kpi-grid">{"".join(items)}</div>', unsafe_allow_html=True)


def comment_card(month: int, mentor_id: str, comment: str, progress: float, readiness: float) -> None:
    st.markdown(
        f"""
        <div class="comment-card">
            <div class="comment-head">
                <div>
                    <div class="comment-month">Месяц {month}</div>
                    <div class="comment-meta">Наставник {escape(str(mentor_id))}</div>
                </div>
                <div>
                    <span class="pill">Прогресс {progress:g}/5</span>
                    <span class="pill pill-green">Готовность {readiness:g}/10</span>
                </div>
            </div>
            <div class="comment-text">«{escape(str(comment))}»</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
