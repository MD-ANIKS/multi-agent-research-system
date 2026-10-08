"""
Streamlit frontend for the multi-agent research platform.

All research logic stays in pipeline.py. This file collects a topic, calls
run_research_pipeline(topic), normalises the returned dictionary with the
backend's extract_clean_text helper, and presents it.

Launch with:  streamlit run app.py
"""

import html
import math
import os
import re
import threading
import time
import traceback
from datetime import datetime

import streamlit as st

try:  # keys are read server-side from .env and never rendered
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from pipeline import run_research_pipeline

    IMPORT_ERROR = None
except Exception as exc:
    run_research_pipeline = None
    IMPORT_ERROR = exc

# Prefer the backend's own extraction helper; fall back to an identical copy
# so the UI still works if the import name ever changes.
try:
    from pipeline import extract_clean_text
except Exception:

    def extract_clean_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        return str(content)


st.set_page_config(page_title="Meridian · Research platform", page_icon="🧭",
                   layout="wide", initial_sidebar_state="expanded")

AGENTS = [
    ("Search", "Finds recent, reliable sources.", "search_results"),
    ("Reader", "Extracts depth from the best page.", "scraped_content"),
    ("Writer", "Drafts the structured report.", "report"),
    ("Critic", "Reviews and flags weak spots.", "feedback"),
]
# pipeline.py returns only when all stages finish, so live stage markers are
# estimates (seconds at which each stage is assumed to start). Results are exact.
STAGE_STARTS = [0, 20, 50, 90]
EXAMPLES = [
    "Solid-state batteries and the future of electric vehicles",
    "Where retrieval-augmented generation is heading",
    "How remote work is reshaping city economies",
]
TEXT_SIZES = {"Compact": "1.0rem", "Comfortable": "1.1rem", "Large": "1.25rem"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap');
:root{--midnight:#0A1020;--deep:#111B33;--canvas:#F4F5F8;--card:#FFFFFF;--ink:#0F172A;--muted:#5B6478;--line:#E1E4EC;
--blue:#2F54EB;--blue-soft:#E4EAFF;--mint:#17B890;--amber:#C27803;--amber-soft:#FDF3DC;
--sans:'Manrope',system-ui,sans-serif;--serif:'Newsreader',Georgia,serif}
html,body,.stApp{color-scheme:light;font-family:var(--sans)}
.stApp{background:var(--canvas)}
#MainMenu,footer{visibility:hidden}
header[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1180px;padding-top:1.6rem;padding-bottom:4rem}
.stApp,.stApp p,.stApp li,.stApp label,.stApp span,.stApp [data-testid="stMarkdownContainer"]{color:var(--ink)}
.stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] *{color:var(--muted)}
.stApp h1,.stApp h2,.stApp h3,.stApp h4{font-family:var(--sans);color:var(--ink);letter-spacing:-.02em}

/* Sidebar */
[data-testid="stSidebar"]{background:var(--midnight);border-right:1px solid #1B2745}
.stApp [data-testid="stSidebar"] *{color:#DCE3F5}
.stApp [data-testid="stSidebar"] hr{border-color:#1F2B4D}
.brand{font-weight:800;font-size:1.35rem;letter-spacing:-.03em;display:flex;align-items:center;gap:.55rem}
.brand i{width:26px;height:26px;border-radius:8px;background:conic-gradient(from 210deg,#2F54EB,#17B890,#2F54EB);display:inline-block}
.stApp [data-testid="stSidebar"] .sub{color:#8F9BBA;font-size:.82rem;margin:.35rem 0 1.1rem}
.stApp [data-testid="stSidebar"] .stButton>button{background:rgba(255,255,255,.05);border:1px solid #243053;border-radius:10px;text-align:left;font-size:.85rem}
.stApp [data-testid="stSidebar"] .stButton>button:hover{border-color:#5B7BFF;background:rgba(91,123,255,.12)}
.stApp [data-testid="stSidebar"] button[kind="primary"]{background:var(--blue);border-color:var(--blue)}
.stApp [data-testid="stSidebar"] .note{color:#8F9BBA;font-size:.78rem;line-height:1.5}

/* Hero band */
[class*="st-key-hero"]{background:radial-gradient(1200px 400px at 85% -20%,#22357A 0%,transparent 60%),linear-gradient(160deg,var(--midnight),var(--deep));
border-radius:20px;padding:2rem 2.2rem 1.8rem;margin-bottom:1.4rem}
.stApp [class*="st-key-hero"] *{color:#EAF0FF}
.stApp [class*="st-key-hero"] .muted{color:#9AA8CB}
.chip{display:inline-flex;align-items:center;gap:.45rem;font-size:.8rem;font-weight:600;padding:.28rem .7rem;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14)}
.chip b{width:7px;height:7px;border-radius:50%;background:var(--mint);display:inline-block}
.chip.run b{background:#6F8DFF;animation:blink 1.2s ease-in-out infinite}
.htitle{font-weight:800;font-size:2.35rem;line-height:1.1;letter-spacing:-.03em;margin:.9rem 0 .4rem;max-width:26ch}
.hsub{font-size:1.02rem;max-width:58ch;line-height:1.55;margin:0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(255,255,255,.12);border-radius:14px;overflow:hidden;margin-top:1.5rem}
.kpi{background:rgba(10,16,32,.55);padding:.9rem 1.1rem}
.kpi .v{font-size:1.55rem;font-weight:700;letter-spacing:-.02em}
.kpi .l{font-size:.78rem;margin-top:.1rem}
.timer{font-size:3rem;font-weight:800;letter-spacing:-.03em;margin:.3rem 0 0;font-variant-numeric:tabular-nums}

/* Agent pipeline */
.track{--t-ink:var(--ink);--t-muted:var(--muted);--t-line:var(--line);--t-bg:var(--card);display:grid;grid-template-columns:repeat(4,1fr);gap:.8rem;margin:1.2rem 0 0}
.track.dark{--t-ink:#EAF0FF;--t-muted:#9AA8CB;--t-line:rgba(255,255,255,.18);--t-bg:rgba(255,255,255,.04)}
.step{border:1px solid var(--t-line);background:var(--t-bg);border-radius:14px;padding:.95rem 1rem}
.step .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:.55rem}
.dot{width:18px;height:18px;border-radius:50%;border:2px solid var(--t-line);position:relative}
.step.done .dot{background:var(--mint);border-color:var(--mint)}
.step.done .dot::after{content:'';position:absolute;left:4px;top:0;width:4px;height:9px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}
.step.active{border-color:#5B7BFF;box-shadow:0 0 0 1px #5B7BFF,0 8px 28px rgba(47,84,235,.25)}
.step.active .dot{border-color:#6F8DFF;animation:pulse 1.5s ease-out infinite}
.stApp .track .step h4{font-size:.98rem;font-weight:700;margin:0;color:var(--t-ink)}
.stApp .track .step p{font-size:.82rem;line-height:1.4;margin:.2rem 0 0;color:var(--t-muted)}
.stApp .track .step .st{font-size:.75rem;font-weight:600;color:var(--t-muted)}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(111,141,255,.55)}100%{box-shadow:0 0 0 10px rgba(111,141,255,0)}}
@keyframes blink{50%{opacity:.25}}
@media (prefers-reduced-motion:reduce){.step.active .dot,.chip.run b{animation:none}}
@media (max-width:820px){.track,.kpis{grid-template-columns:1fr 1fr}.htitle{font-size:1.8rem}}

/* Composer */
[class*="st-key-composer"]{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.3rem 1.4rem .6rem;box-shadow:0 10px 40px rgba(15,23,42,.06)}
[data-testid="stForm"]{border:none;padding:0}
.stTextInput input{background:#fff!important;color:var(--ink)!important;border:1px solid var(--line)!important;border-radius:12px;font-size:1.05rem;padding:.8rem 1rem}
.stTextInput input:focus{border-color:var(--blue)!important;box-shadow:0 0 0 4px var(--blue-soft)!important}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{border-radius:11px;border:1px solid var(--line);background:var(--card);color:var(--ink);font-weight:600;transition:border-color .15s,background .15s}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:var(--blue);color:var(--blue)}
button[kind="primary"],button[kind="primaryFormSubmit"]{background:var(--blue)!important;border-color:var(--blue)!important;color:#fff!important}
button[kind="primary"] *,button[kind="primaryFormSubmit"] *{color:#fff!important}
button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover{background:#2443C4!important}
.stButton>button:focus-visible,.stDownloadButton>button:focus-visible{outline:3px solid var(--blue-soft)}

/* Tabs and content */
.stTabs [data-baseweb="tab-list"]{gap:1.6rem;border-bottom:1px solid var(--line)}
.stTabs [data-baseweb="tab"]{padding:.7rem 0;font-weight:600;color:var(--muted)}
.stTabs [aria-selected="true"]{color:var(--blue)!important}
.stTabs [data-baseweb="tab-highlight"]{background:var(--blue)}
[class*="st-key-report-card"],[class*="st-key-critic-card"],[class*="st-key-source-card"]{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:1.8rem 2.2rem}
[class*="st-key-report-card"] [data-testid="stMarkdownContainer"]{font-family:var(--serif);line-height:1.75}
[class*="st-key-report-card"] [data-testid="stMarkdownContainer"]>*{max-width:68ch}
[class*="st-key-report-card"] h1,[class*="st-key-report-card"] h2,[class*="st-key-report-card"] h3{font-family:var(--sans);margin-top:1.7rem}
[class*="st-key-critic-card"]{border-left:5px solid var(--amber);background:#FFFEFB}
[class*="st-key-source-card"] [data-testid="stMarkdownContainer"]{font-size:.97rem;line-height:1.65}
.toc{position:sticky;top:4rem;border:1px solid var(--line);background:var(--card);border-radius:14px;padding:1rem 1.1rem;margin-bottom:1rem}
.toc .h{font-weight:700;font-size:.88rem;margin-bottom:.5rem}
.toc a{display:block;font-size:.85rem;line-height:1.35;padding:.28rem 0;color:var(--muted)!important;text-decoration:none}
.toc a:hover{color:var(--blue)!important}
.toc a.l2{padding-left:.8rem}.toc a.l3{padding-left:1.6rem}
.note-row{color:var(--muted);font-size:.9rem;margin:1rem 0 .8rem}
.err{background:#FDEEEA;border:1px solid #F0C0B6;border-left:5px solid #C23B22;border-radius:14px;padding:1.1rem 1.3rem;margin:1rem 0}
.sec{font-weight:700;font-size:1.05rem;margin:2rem 0 .2rem}
</style>
"""


# ------------------------------- helpers ---------------------------------- #

def as_text(value) -> str:
    """Normalise any agent output (string, content blocks, message object) via the backend helper."""
    if value is None:
        return ""
    if not isinstance(value, (str, list)) and hasattr(value, "content"):
        value = value.content
    return extract_clean_text(value)


def scrub(text: str) -> str:
    for name, val in os.environ.items():
        if val and len(val) >= 8 and any(t in name.upper() for t in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            text = text.replace(val, "[hidden]")
    return text


def slugify(text: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]) or "research-report"


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def words(text: str) -> int:
    return len(text.split())


def stage_for(elapsed: float) -> int:
    return max(i for i, s in enumerate(STAGE_STARTS) if elapsed >= s)


def track_html(active=None, all_done=False, result=None, dark=False) -> str:
    parts = []
    for i, (name, desc, key) in enumerate(AGENTS):
        cls = "done" if all_done or (active is not None and i < active) else (
            "active" if active == i else "idle")
        status = {"done": "Done", "active": "Working", "idle": "Waiting" if active is not None else "Ready"}[cls]
        detail = f"{words(result.get(key, '')):,} words produced" if result and all_done else desc
        parts.append(
            f'<div class="step {cls}"><div class="top"><div class="dot"></div><span class="st">{status}</span></div>'
            f"<h4>{html.escape(name)} Agent</h4><p>{html.escape(detail)}</p></div>")
    return f'<div class="track{" dark" if dark else ""}">{"".join(parts)}</div>'


def outline(report: str) -> str:
    items = []
    for hashes, title in re.findall(r"^(#{1,3})\s+(.+?)\s*$", report, re.M)[:14]:
        clean = re.sub(r"[*_`]", "", title)
        anchor = re.sub(r"[^\w\- ]", "", clean.lower()).strip().replace(" ", "-")
        items.append(f'<a class="l{len(hashes)}" href="#{anchor}">{html.escape(clean)}</a>')
    return f'<div class="toc"><div class="h">On this page</div>{"".join(items)}</div>' if items else ""


def bundle(topic: str, r: dict) -> str:
    return (f"# {topic}\n\n## Report\n\n{r['report']}\n\n## Critic review\n\n{r['feedback']}\n\n"
            f"## Search results\n\n{r['search_results']}\n\n## Deep research\n\n{r['scraped_content']}\n")


# --------------------------- state and job control ------------------------- #

def init_state():
    for k, v in {"status": "idle", "topic": "", "result": None, "error": None, "job": None,
                 "started": 0.0, "elapsed": 0.0, "history": [], "error_trace": ""}.items():
        st.session_state.setdefault(k, v)


def _worker(topic: str, box: dict):
    try:
        box["result"] = run_research_pipeline(topic)
    except Exception as exc:
        box["error"] = f"{type(exc).__name__}: {exc}"
        box["trace"] = traceback.format_exc()
    finally:
        box["done"] = True


def start_research(topic: str):
    topic = (topic or "").strip()
    if not topic or run_research_pipeline is None:
        return
    box = {"done": False}
    t = threading.Thread(target=_worker, args=(topic, box), daemon=True)
    st.session_state.update(status="running", topic=topic, result=None, error=None,
                            job={"thread": t, "box": box}, started=time.time())
    t.start()


def new_research():
    st.session_state.update(status="idle", topic="", result=None, error=None, job=None, topic_input="")


def open_past(i: int):
    item = st.session_state.history[i]
    st.session_state.update(status="done", topic=item["topic"], result=item["result"],
                            elapsed=item["elapsed"], error=None)


def finish_job():
    box = st.session_state.job["box"]
    st.session_state.elapsed = time.time() - st.session_state.started
    if "error" in box:
        st.session_state.update(status="error", error=scrub(box["error"]), job=None,
                                error_trace=scrub(box.get("trace", "")))
        return
    raw = box.get("result")
    if not isinstance(raw, dict):
        st.session_state.update(status="error", job=None, error_trace="",
                                error="The pipeline did not return a result dictionary.")
        return
    result = {k: as_text(raw.get(k)) for _, _, k in AGENTS}
    if not result["report"].strip():
        st.session_state.update(status="error", job=None, error_trace="",
                                error="The pipeline finished but the report is empty. Check pipeline.py and your agent configuration.")
        return
    st.session_state.update(status="done", result=result, job=None)
    st.session_state.history.insert(0, {"topic": st.session_state.topic, "result": result,
                                        "elapsed": st.session_state.elapsed, "at": datetime.now().strftime("%H:%M")})
    del st.session_state.history[10:]


# --------------------------------- views ----------------------------------- #

def render_sidebar():
    running = st.session_state.status == "running"
    with st.sidebar:
        st.markdown('<div class="brand"><i></i>Meridian</div>'
                    '<div class="sub">Multi-agent research platform</div>', unsafe_allow_html=True)
        st.button("New research", type="primary", use_container_width=True,
                  on_click=new_research, disabled=running)
        st.markdown("---")
        if st.session_state.history:
            st.markdown("**Recent runs**")
            for i, item in enumerate(st.session_state.history):
                label = item["topic"] if len(item["topic"]) <= 34 else item["topic"][:32] + "…"
                st.button(f"{label} · {item['at']}", key=f"hist_{i}", use_container_width=True,
                          on_click=open_past, args=(i,), disabled=running)
        else:
            st.markdown('<div class="note">Completed runs from this session appear here.</div>',
                        unsafe_allow_html=True)
   


def view_idle():
    with st.container(key="hero"):
        st.markdown('<span class="chip"><b></b>Four agents online</span>'
                    '<div class="htitle">Research that searches, reads, writes and reviews itself.</div>'
                    '<p class="hsub muted">Enter a topic. A search, reader, writer and critic agent work in sequence '
                    "and hand you a sourced report with an independent critique.</p>", unsafe_allow_html=True)
        st.markdown(track_html(None, dark=True), unsafe_allow_html=True)

    if IMPORT_ERROR is not None:
        st.markdown('<div class="err"><b>The research pipeline could not be loaded.</b><br>'
                    f"{html.escape(scrub(f'{type(IMPORT_ERROR).__name__}: {IMPORT_ERROR}'))}<br>"
                    "Check agents.py, tools.py and your .env keys, then reload.</div>", unsafe_allow_html=True)

    with st.container(key="composer"):
        with st.form("topic_form", border=False):
            st.text_input("Research topic", key="topic_input",
                          placeholder="e.g. How are small modular reactors changing energy policy?")
            st.form_submit_button("Start research", type="primary", disabled=IMPORT_ERROR is not None,
                                  on_click=lambda: start_research(st.session_state.get("topic_input", "")))
    st.caption("Try an example")
    for col, ex in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(ex, key=f"ex_{ex}", use_container_width=True, on_click=start_research,
                   args=(ex,), disabled=IMPORT_ERROR is not None)


def view_running():
    box = st.session_state.job["box"]
    with st.container(key="hero"):
        st.markdown('<span class="chip run"><b></b>Research in progress</span>'
                    f'<div class="htitle">{html.escape(st.session_state.topic)}</div>'
                    '<p class="hsub muted">Keep this tab open. Results appear together when the critic finishes.</p>',
                    unsafe_allow_html=True)
        timer_ph, track_ph, note_ph = st.empty(), st.empty(), st.empty()
        while not box["done"]:
            elapsed = time.time() - st.session_state.started
            active = stage_for(elapsed)
            timer_ph.markdown(f'<div class="timer">{clock(elapsed)}</div>', unsafe_allow_html=True)
            track_ph.markdown(track_html(active, dark=True), unsafe_allow_html=True)
            note_ph.markdown(f'<p class="muted" style="font-size:.85rem;margin-top:1rem">'
                             f"Now: {AGENTS[active][0]} Agent. Stage markers are estimates; the final results are exact.</p>",
                             unsafe_allow_html=True)
            time.sleep(0.5)
    finish_job()
    st.rerun()


def view_error():
    st.markdown(f'<div class="err"><b>The research run failed.</b><br>{html.escape(st.session_state.error or "Unknown error")}'
                "<br><br>Common causes: a missing or invalid API key in .env, a rate limit, or a network issue. "
                "Fix the cause, then try again.</div>", unsafe_allow_html=True)
    if st.session_state.error_trace:
        with st.expander("Technical details"):
            st.code(st.session_state.error_trace, language="text")
    c1, c2, _ = st.columns([1, 1, 3])
    c1.button("Try again", type="primary", on_click=start_research, args=(st.session_state.topic,))
    c2.button("New research", on_click=new_research)


def view_done():
    topic, r = st.session_state.topic, st.session_state.result
    rw = words(r["report"])
    analysed = words(r["search_results"]) + words(r["scraped_content"])
    with st.container(key="hero"):
        st.markdown('<span class="chip"><b></b>Research complete</span>'
                    f'<div class="htitle">{html.escape(topic)}</div>'
                    f'<div class="kpis">'
                    f'<div class="kpi"><div class="v">{rw:,}</div><div class="l muted">Words in report</div></div>'
                    f'<div class="kpi"><div class="v">{max(1, math.ceil(rw / 220))} min</div><div class="l muted">Reading time</div></div>'
                    f'<div class="kpi"><div class="v">{analysed:,}</div><div class="l muted">Words of research gathered</div></div>'
                    f'<div class="kpi"><div class="v">{clock(st.session_state.elapsed)}</div><div class="l muted">Total run time</div></div>'
                    "</div>", unsafe_allow_html=True)
        st.markdown(track_html(all_done=True, result=r, dark=True), unsafe_allow_html=True)

    slug = slugify(topic)
    c1, c2, c3, _ = st.columns([1.2, 1.3, 1.1, 1.2])
    c1.download_button("Download report", r["report"], file_name=f"{slug}.md", mime="text/markdown",
                       type="primary", use_container_width=True)
    c2.download_button("Download full dossier", bundle(topic, r), file_name=f"{slug}-dossier.md",
                       mime="text/markdown", use_container_width=True)
    c3.button("New research", on_click=new_research, use_container_width=True)

    t_report, t_critic, t_search, t_deep = st.tabs(["Report", "Critic review", "Search results", "Deep research"])

    with t_report:
        main_col, side_col = st.columns([3, 1], gap="large")
        with side_col:
            size = st.select_slider("Text size", options=list(TEXT_SIZES), value="Comfortable")
            st.markdown(outline(r["report"]), unsafe_allow_html=True)
        with main_col:
            st.markdown('<style>[class*="st-key-report-card"] [data-testid="stMarkdownContainer"]'
                        f"{{font-size:{TEXT_SIZES[size]}}}</style>", unsafe_allow_html=True)
            with st.container(key="report-card"):
                st.markdown(r["report"])
    with t_critic:
        st.markdown('<div class="note-row">An independent review of the draft. Use it to judge how far to trust the report.</div>',
                    unsafe_allow_html=True)
        with st.container(key="critic-card"):
            st.markdown(r["feedback"] or "_The critic returned no feedback._")
    with t_search:
        st.markdown('<div class="note-row">What the search agent found. The reader agent chose its source from here.</div>',
                    unsafe_allow_html=True)
        with st.container(key="source-card-search"):
            st.markdown(r["search_results"] or "_No search results were returned._")
    with t_deep:
        st.markdown('<div class="note-row">Full content the reader agent extracted from the most relevant page.</div>',
                    unsafe_allow_html=True)
        with st.container(key="source-card-deep"):
            st.markdown(r["scraped_content"] or "_No scraped content was returned._")


def main():
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    render_sidebar()
    s = st.session_state
    if s.status == "running" and s.job:
        view_running()
    elif s.status == "done" and s.result:
        view_done()
    elif s.status == "error":
        view_error()
    else:
        view_idle()


main()