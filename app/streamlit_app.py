"""Streamlit UI for the semiconductor fab maintenance assistant.

Imports the agent loop directly — no HTTP boundary needed since Streamlit
runs in the same Python process.

Launch:
    uv run streamlit run app/streamlit_app.py
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from agent.loop import run
from agent.traces import Tracer

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Fab Maintenance Assistant",
    page_icon="🔧",
    layout="wide",
)

st.markdown("""
<style>
/* Top toolbar — Lam grey */
header[data-testid="stHeader"] { background-color: #6F7884; }

/* Sidebar — Lam navy */
[data-testid="stSidebar"] { background-color: #252436 !important; border-top: none; }
[data-testid="stSidebar"] h2 { color: #9CE0C7 !important; font-weight: 600; }
[data-testid="stSidebar"] label { color: rgba(255,255,255,0.85) !important; }
[data-testid="stSidebar"] p { color: #9CE0C7 !important; }
[data-testid="stSidebar"] input {
    color: #252436 !important;
    border-color: rgba(156,224,199,0.35) !important;
}
[data-testid="stSidebar"] input::placeholder { color: rgba(37,36,54,0.45) !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.15) !important; opacity: 1; }

/* Main panel dividers — Lam grey */
.main hr { border-color: #6F7884 !important; opacity: 0.3; }

/* Metric values (confidence %) — Lam navy, bold */
[data-testid="stMetricValue"] { color: #252436 !important; font-weight: 700; }

/* Captions — Lam grey */
.stCaption, [data-testid="stCaptionContainer"] p { color: #6F7884 !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar — optional filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Search filters")
    st.caption("Narrow the retrieval scope. Leave blank to search all records.")

    tool_id = st.text_input("Tool ID", placeholder="e.g. ETCH02")
    subsystem = st.text_input("Subsystem", placeholder="e.g. rf_source")

    st.divider()
    st.caption("© 2026 intuitiveengineer")

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

st.markdown("""
<div style="background-color:#252436; padding:1.25rem 1.5rem; border-radius:6px; margin-bottom:1.25rem;">
    <h1 style="color:#FFFFFF; margin:0; padding:0; font-size:1.9rem;">🔧 Semiconductor Fab Maintenance Assistant</h1>
    <p style="color:#9CE0C7; margin:0.35rem 0 0 0; font-size:0.95rem; opacity:0.9;">
        Describe an equipment symptom — the agent retrieves relevant maintenance records and returns a structured diagnosis.
    </p>
</div>
""", unsafe_allow_html=True)

query = st.text_area(
    "Symptom description",
    placeholder="e.g. ETCH02 is showing etch-rate drift and across-wafer non-uniformity after the last PM.",
    height=100,
)

run_button = st.button("Diagnose", type="primary", disabled=not query.strip())

# ---------------------------------------------------------------------------
# Run the agent
# ---------------------------------------------------------------------------

if run_button and query.strip():
    tracer = Tracer()

    # Prepend any sidebar filters as context so the agent picks them up naturally.
    full_query = query.strip()
    hints = []
    if tool_id.strip():
        hints.append(f"Tool: {tool_id.strip()}")
    if subsystem.strip():
        hints.append(f"Subsystem of concern: {subsystem.strip()}")
    if hints:
        full_query = f"{', '.join(hints)}. {full_query}"

    with st.spinner("Agent is working — calling tools and retrieving documents..."):
        try:
            diagnosis = run(full_query, tracer=tracer)
            tracer.save()
            st.session_state["diagnosis"] = diagnosis
            st.session_state["trace"] = tracer.to_dict()
            st.session_state["error"] = None
        except Exception as exc:
            st.session_state["diagnosis"] = None
            st.session_state["trace"] = None
            st.session_state["error"] = str(exc)

# ---------------------------------------------------------------------------
# Render results
# ---------------------------------------------------------------------------

if st.session_state.get("error"):
    st.error(f"Agent error: {st.session_state['error']}")

elif st.session_state.get("diagnosis"):
    diagnosis = st.session_state["diagnosis"]
    trace = st.session_state["trace"]

    st.divider()

    # Summary
    st.subheader("Summary")
    st.info(diagnosis.summary)

    # Overall confidence
    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric("Overall confidence", f"{diagnosis.confidence:.0%}")

    st.divider()

    # Likely causes
    st.subheader("Likely causes")
    for i, cause in enumerate(diagnosis.likely_causes, 1):
        with st.container():
            cols = st.columns([1, 8])
            with cols[0]:
                st.metric(label="", value=f"{cause.confidence:.0%}")
            with cols[1]:
                st.markdown(f"**{cause.cause}**")
                st.caption(f"Evidence: {', '.join(cause.evidence_doc_ids)}")
            st.progress(cause.confidence)

    st.divider()

    # Recommended checks
    st.subheader("Recommended checks")
    for check in diagnosis.recommended_checks:
        st.markdown(f"- {check}")

    st.divider()

    # Citations
    st.subheader("Citations")
    st.markdown(" · ".join(f"`{c}`" for c in diagnosis.citations))

    # Trace expander
    if trace:
        tool_calls = trace.get("tool_calls", [])
        with st.expander(f"Tool calls ({len(tool_calls)})", expanded=False):
            for tc in tool_calls:
                st.markdown(f"**`{tc['name']}`** ({tc['latency_ms']} ms)")
                st.json({"args": tc["args"], "result": tc["result"]})

        with st.expander("Run metadata", expanded=False):
            st.json({
                "run_id":          trace["run_id"],
                "iterations":      trace["iterations"],
                "total_latency_ms": trace["total_latency_ms"],
                "usage":           trace["usage"],
            })
