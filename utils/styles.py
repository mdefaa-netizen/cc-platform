import streamlit as st
from html import escape as _esc

PALETTE = {
    "navy":    "#1B2A4A",
    "teal":    "#2A7F7F",
    "gold":    "#C8963E",
    "cream":   "#F5F0E8",
    "white":   "#FFFFFF",
    "red":     "#C0392B",
    "green":   "#27AE60",
    "blue":    "#2980B9",
    "gray":    "#7F8C8D",
    "lt_gray": "#ECF0F1",
}

PROGRAM_TITLE = "NH Humanities & CDFA · Community Conversations"

def inject_css():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Sans+3:wght@300;400;600&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Source Sans 3', sans-serif;
        background-color: {PALETTE['cream']};
        color: {PALETTE['navy']};
    }}

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {{
        background-color: {PALETTE['navy']} !important;
    }}
    section[data-testid="stSidebar"] * {{
        color: {PALETTE['white']} !important;
    }}

    /* ── Program title (Red Zone 2 — bigger font) ── */
    .program-title {{
        font-size: 1.15rem !important;
        font-weight: 800;
        color: {PALETTE['teal']};
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 0.15rem;
        margin-top: 0.3rem;
        font-family: 'Source Sans 3', sans-serif;
        display: block;
    }}

    /* ── Page title ── */
    h1 {{
        font-family: 'Playfair Display', serif;
        color: {PALETTE['navy']};
        font-size: 2rem;
        border-bottom: 3px solid {PALETTE['gold']};
        padding-bottom: 0.3rem;
        margin-top: 0.1rem !important;
        margin-bottom: 0.2rem !important;
    }}
    .page-subtitle {{
        color: {PALETTE['gray']};
        font-size: 0.88rem;
        margin-top: 0 !important;
        margin-bottom: 1rem !important;
        display: block;
    }}
    h2, h3 {{
        font-family: 'Playfair Display', serif;
        color: {PALETTE['navy']};
    }}

    /* ── KPI cards (Red Zone 4 — smaller) ── */
    .kpi-card {{
        background: {PALETTE['white']};
        border-radius: 8px;
        padding: 0.7rem 1rem;
        border-left: 4px solid {PALETTE['teal']};
        box-shadow: 0 2px 6px rgba(0,0,0,0.07);
        margin-bottom: 0.5rem;
    }}
    .kpi-card.gold  {{ border-left-color: {PALETTE['gold']}; }}
    .kpi-card.red   {{ border-left-color: {PALETTE['red']}; }}
    .kpi-card.green {{ border-left-color: {PALETTE['green']}; }}
    .kpi-label {{
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: {PALETTE['gray']};
        margin-bottom: 0.1rem;
    }}
    .kpi-value {{
        font-size: 1.6rem;
        font-weight: 700;
        color: {PALETTE['navy']};
        line-height: 1.1;
    }}
    .kpi-sub {{
        font-size: 0.72rem;
        color: {PALETTE['gray']};
        margin-top: 0.1rem;
    }}

    /* ── Overdue task cards (Red Zone 3 — smaller) ── */
    .overdue-card {{
        background: #FADBD8;
        border-radius: 6px;
        padding: 0.4rem 0.7rem;
        margin-bottom: 0.35rem;
        border-left: 3px solid {PALETTE['red']};
    }}
    .overdue-title {{
        font-weight: 600;
        font-size: 0.82rem;
        color: {PALETTE['navy']};
    }}
    .overdue-meta {{
        font-size: 0.72rem;
        color: #922B21;
    }}

    /* ── Badges ── */
    .badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }}
    .badge-scheduled {{ background:#D6EAF8; color:#1A5276; }}
    .badge-completed {{ background:#D5F5E3; color:#1E8449; }}
    .badge-cancelled {{ background:#FADBD8; color:#922B21; }}
    .badge-pending   {{ background:#FEF9E7; color:#9A7D0A; }}
    .badge-approved  {{ background:#EBF5FB; color:#1A5276; }}
    .badge-paid      {{ background:#D5F5E3; color:#1E8449; }}
    .badge-low    {{ background:#EAFAF1; color:#1E8449; }}
    .badge-medium {{ background:#EBF5FB; color:#1A5276; }}
    .badge-high   {{ background:#FEF9E7; color:#9A7D0A; }}
    .badge-urgent {{ background:#FADBD8; color:#922B21; }}

    /* ── Section boxes ── */
    .section-box {{
        background: {PALETTE['white']};
        border-radius: 8px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
        margin-bottom: 0.8rem;
    }}

    /* ── Buttons ── */
    .stButton > button {{
        background-color: {PALETTE['teal']};
        color: white;
        border: none;
        border-radius: 6px;
        font-family: 'Source Sans 3', sans-serif;
        font-weight: 600;
        padding: 0.35rem 1rem;
        transition: background 0.2s;
    }}
    .stButton > button:hover {{
        background-color: {PALETTE['navy']};
    }}

    /* ── Feed items ── */
    .feed-item {{
        padding: 0.5rem 0;
        border-bottom: 1px solid {PALETTE['lt_gray']};
        font-size: 0.85rem;
    }}
    .feed-item:last-child {{ border-bottom: none; }}
    .feed-date {{
        font-size: 0.73rem;
        color: {PALETTE['gray']};
    }}

    /* ── Alert boxes ── */
    .alert-danger {{
        background: #FADBD8;
        border-left: 4px solid {PALETTE['red']};
        padding: 0.7rem 0.9rem;
        border-radius: 0 6px 6px 0;
        margin-bottom: 0.7rem;
        font-size: 0.88rem;
    }}

    /* ── Top nav bar ── */
    .top-nav-wrap {{
        background: {PALETTE['navy']};
        padding: 0.3rem 0.5rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
    }}
    .top-nav-wrap .stButton > button {{
        background: transparent !important;
        color: #cbd5e1 !important;
        border: none !important;
        font-size: 0.72rem !important;
        padding: 0.2rem 0.3rem !important;
        font-weight: 600;
        white-space: nowrap;
    }}
    .top-nav-wrap .stButton > button:hover {{
        background: rgba(255,255,255,0.15) !important;
        color: white !important;
    }}
    .top-nav-wrap [data-testid="stPageLink"] a {{
        color: #cbd5e1 !important;
        font-size: 0.72rem !important;
        font-weight: 600;
        text-decoration: none;
        padding: 0.2rem 0.3rem;
        border-radius: 4px;
        display: block;
        text-align: center;
    }}
    .top-nav-wrap [data-testid="stPageLink"] a:hover {{
        background: rgba(255,255,255,0.15);
        color: white !important;
    }}

    /* Sidebar collapsed by default - still accessible */
    #MainMenu {{ visibility: hidden; }}
    footer    {{ visibility: hidden; }}
    .stMainBlockContainer {{ max-width: 100% !important; }}
    </style>
    """, unsafe_allow_html=True)

def top_nav():
    pass  # Navigation handled by sidebar


def page_header(title, subtitle=None):
    top_nav()
    st.markdown(f'<span class="program-title">{_esc(PROGRAM_TITLE)}</span>', unsafe_allow_html=True)
    st.markdown(f"<h1>{_esc(title)}</h1>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<span class="page-subtitle">{_esc(subtitle)}</span>', unsafe_allow_html=True)

def kpi_card(label, value, sub="", color="teal"):
    safe_color = _esc(str(color))
    st.markdown(f"""
    <div class="kpi-card {safe_color}">
        <div class="kpi-label">{_esc(str(label))}</div>
        <div class="kpi-value">{_esc(str(value))}</div>
        {"<div class='kpi-sub'>" + _esc(str(sub)) + "</div>" if sub else ""}
    </div>
    """, unsafe_allow_html=True)

def status_badge(status):
    cls = f"badge-{status.lower().replace(' ','-')}"
    return f'<span class="badge {cls}">{status}</span>'

def priority_badge(priority):
    cls = f"badge-{priority.lower()}"
    return f'<span class="badge {cls}">{priority}</span>'
