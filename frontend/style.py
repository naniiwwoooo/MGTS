"""Оформление дашборда в стиле apple.com: CSS и HTML-компоненты."""

from __future__ import annotations

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

/* Hero */
.hero { text-align: center; padding: 1rem 0 2.6rem; }
.hero-eyebrow {
    color: var(--apple-blue);
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.09em;
    text-transform: uppercase;
}
.hero-title {
    font-size: clamp(2.5rem, 6vw, 4rem);
    font-weight: 700;
    letter-spacing: -0.035em;
    line-height: 1.05;
    margin: 0.5rem 0 0.7rem;
}
.hero-sub {
    color: var(--muted);
    font-size: 1.12rem;
    line-height: 1.5;
    max-width: 640px;
    margin: 0 auto;
}

/* Sections */
.section { margin-top: 2.9rem; }
.section-title {
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin: 0 0 0.15rem;
}
.section-sub {
    color: var(--muted);
    font-size: 0.95rem;
    margin: 0 0 1rem;
}

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
    transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.07);
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

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    border-bottom: 1px solid var(--line);
}
.stTabs [data-baseweb="tab"] {
    height: 46px;
    padding: 0 20px;
    background: transparent;
    font-weight: 600;
    font-size: 0.98rem;
    color: var(--muted);
}
.stTabs [aria-selected="true"] { color: var(--ink); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--apple-blue); }

/* AI block */
.ai-card {
    background: linear-gradient(135deg, #f5f5f7 0%, #eef4ff 100%);
    border-radius: 24px;
    padding: 26px 28px;
    margin-top: 2.4rem;
}
.ai-title {
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin-bottom: 0.4rem;
}
.ai-text { color: var(--muted); font-size: 0.96rem; line-height: 1.5; max-width: 680px; }
.ai-badge {
    display: inline-block;
    background: rgba(0, 113, 227, 0.12);
    color: var(--apple-blue);
    border-radius: 999px;
    padding: 3px 11px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: 0.7rem;
}

/* Selectbox */
div[data-baseweb="select"] > div {
    border-radius: 14px;
    border-color: var(--line);
    background: var(--surface-2);
}

/* Metric widget fallback */
[data-testid="stMetricValue"] { font-weight: 700; letter-spacing: -0.02em; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-eyebrow">{eyebrow}</div>
            <h1 class="hero-title">{title}</h1>
            <p class="hero-sub">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str | None = None) -> None:
    sub = f'<p class="section-sub">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="section"><div class="section-title">{title}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


def kpi_grid(cards: list[dict[str, str]]) -> None:
    """cards: список словарей с ключами label, value, sub (sub опционален)."""
    items = []
    for card in cards:
        sub = f'<div class="kpi-sub">{card["sub"]}</div>' if card.get("sub") else ""
        items.append(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{card["label"]}</div>'
            f'<div class="kpi-value">{card["value"]}</div>'
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
                    <div class="comment-meta">Наставник {mentor_id}</div>
                </div>
                <div>
                    <span class="pill">Прогресс {progress:g}/5</span>
                    <span class="pill pill-green">Готовность {readiness:g}/10</span>
                </div>
            </div>
            <div class="comment-text">«{comment}»</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ai_block(title: str, text: str, badge: str = "Скоро") -> None:
    st.markdown(
        f"""
        <div class="ai-card">
            <div class="ai-badge">{badge}</div>
            <div class="ai-title">{title}</div>
            <div class="ai-text">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
