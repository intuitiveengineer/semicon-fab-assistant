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

# ---------------------------------------------------------------------------
# Sidebar — optional filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Search filters")
    st.caption("Narrow the retrieval scope. Leave blank to search all records.")

    tool_id = st.text_input("Tool ID", placeholder="e.g. ETCH02")
    subsystem = st.text_input("Subsystem", placeholder="e.g. rf_source")

    st.divider()
    st.caption("Qdrant must be running (`docker compose up -d`).")
    st.caption("OpenAI API key required in `.env`.")

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

st.title("🔧 Semiconductor Fab Maintenance Assistant")
st.caption(
    "Describe an equipment symptom and the agent will retrieve relevant "
    "maintenance records and return a structured diagnosis."
)

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
