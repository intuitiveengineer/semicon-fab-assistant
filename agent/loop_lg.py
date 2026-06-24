"""Agent v1 — LangGraph state-machine implementation.

Same public API as agent/loop.py (identical run() signature, same Diagnosis
output), but the tool-calling loop is expressed as an explicit directed graph
instead of a hand-written for-loop.

How it compares to loop.py
--------------------------
loop.py has three logical phases in one big for-loop:
  1. Call the model
  2. Execute tool calls
  3. Repeat, or break and finalize

loop_lg.py makes those phases explicit as named graph nodes:

    ┌─────────────────────────────────────────────┐
    │                                             │
    │   ┌──────────────┐    tool_calls?           │
    │   │  call_model  │──────────────────────────┘
    │   └──────┬───────┘
    │          │ no tool_calls
    │          │ (or hit max_iterations)
    │   ┌──────▼───────┐    ┌──────────────┐
    │   │   finalize   │    │  exec_tools  │
    │   └──────┬───────┘    └──────┬───────┘
    │          │                   │
    │         END         (loop back to call_model)
    └───────────────────────────────────────────────
         ↑ call_model feeds exec_tools feeds call_model

The _route() function is the conditional edge: it inspects the current state
and decides which node to go to next. In loop.py this logic was implicit in
the `if not msg.tool_calls: break` line.

The benefit of making this explicit is that adding a new branch (e.g., "if
zero results were retrieved, try a broader search before finalizing") is a
matter of adding a node and an edge — not restructuring the whole loop.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config  # noqa: E402  triggers load_dotenv + key validation
from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from agent.schemas import Diagnosis
from agent.tools import TOOLS, dispatch
from agent.traces import Tracer

MODEL = "gpt-4o-mini"
MAX_ITERATIONS = 8

_client = OpenAI()

SYSTEM_PROMPT = """\
You are a semiconductor fab equipment maintenance assistant. Your job is to \
diagnose equipment failures from maintenance records and recommend next steps.

When given a symptom or equipment problem:
1. Use search_maintenance_docs to find relevant work orders, alarm logs, \
   shift notes, and SOPs. Search with the symptom first; then search again \
   narrowed by tool_id or subsystem if you find useful leads.
2. If alarm codes appear in the documents, use lookup_alarm_code to understand them.
3. Use get_tool_status to check open issues and maintenance history for the tool.
4. Use compute_mtbf or get_recent_alarms if timing or overdue PM seems relevant.
5. When you have enough evidence, stop calling tools and provide your diagnosis.

Rules:
- Always call search_maintenance_docs at least once before concluding.
- Every cause in your diagnosis must be supported by at least one doc_id.
- List all doc_ids you read in citations, even if they didn't influence the diagnosis.
- Be specific: name the subsystem, the failure mode, and the fix.
- Confidence should reflect how strongly the evidence points to that cause.\
"""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
# In loop.py the state was implicit: local variables (messages, iteration).
# Here it is a typed dict that flows between nodes. Every node receives the
# current state and returns a dict of fields to update.
#
# Note: tracer is not JSON-serialisable, so LangGraph checkpointing would not
# work with this state as-is. That is fine — we are not using checkpointing.
# ---------------------------------------------------------------------------

class _State(TypedDict):
    messages:       list[dict]
    iteration:      int
    max_iterations: int
    verbose:        bool
    tools_override: list[dict] | None
    tracer:         Any          # Tracer | None
    diagnosis:      Any          # Diagnosis | None


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def _node_call_model(state: _State) -> dict:
    """Call the LLM and append the assistant turn to the message list."""
    active_tools = state["tools_override"] or TOOLS

    response = _client.chat.completions.create(
        model=MODEL,
        messages=state["messages"],
        tools=active_tools,
        tool_choice="auto",
    )
    msg = response.choices[0].message

    assistant_turn: dict = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        assistant_turn["tool_calls"] = [
            {
                "id":   tc.id,
                "type": "function",
                "function": {
                    "name":      tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    else:
        # LLM is done gathering evidence — record the final iteration count.
        tracer = state["tracer"]
        if tracer:
            tracer.record_iteration(state["iteration"] + 1)
        if state["verbose"]:
            print(f"[loop_lg] iteration {state['iteration'] + 1}: LLM finished tool calls")

    return {
        "messages":  state["messages"] + [assistant_turn],
        "iteration": state["iteration"] + 1,
    }


def _node_exec_tools(state: _State) -> dict:
    """Execute every tool call in the last assistant message and append results."""
    last = state["messages"][-1]
    tool_results = []
    tracer  = state["tracer"]
    verbose = state["verbose"]

    for tc in last["tool_calls"]:
        args = json.loads(tc["function"]["arguments"])
        name = tc["function"]["name"]

        if verbose:
            print(f"[tool] {name}({args})")

        t0 = time.time()
        result = dispatch(name, args)
        latency_ms = int((time.time() - t0) * 1000)

        if verbose:
            print(f"       → {json.dumps(result)[:200]}")

        if tracer:
            tracer.record_tool_call(name, args, result, latency_ms)

        tool_results.append({
            "role":         "tool",
            "tool_call_id": tc["id"],
            "content":      json.dumps(result),
        })

    return {"messages": state["messages"] + tool_results}


def _node_finalize(state: _State) -> dict:
    """Make the structured-output call and store the validated Diagnosis."""
    if state["verbose"] and state["iteration"] >= state["max_iterations"]:
        print(f"[loop_lg] hit max_iterations={state['max_iterations']}, forcing final answer")

    final = _client.beta.chat.completions.parse(
        model=MODEL,
        messages=state["messages"],
        response_format=Diagnosis,
    )
    diagnosis = final.choices[0].message.parsed

    tracer = state["tracer"]
    if tracer:
        tracer.finish(diagnosis, final.usage)

    return {"diagnosis": diagnosis}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
# This is the conditional edge out of call_model.
# In loop.py it was the implicit `if not msg.tool_calls: break` check.
# ---------------------------------------------------------------------------

def _route(state: _State) -> Literal["exec_tools", "finalize"]:
    """Decide what to do after the model responds."""
    last = state["messages"][-1]
    has_tool_calls = bool(last.get("tool_calls"))
    hit_cap        = state["iteration"] >= state["max_iterations"]

    if has_tool_calls and not hit_cap:
        return "exec_tools"

    if hit_cap and state["tracer"]:
        state["tracer"].record_iteration(state["max_iterations"])

    return "finalize"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
# Built once at module import time; reused for every run() call.
# ---------------------------------------------------------------------------

_workflow = StateGraph(_State)

_workflow.add_node("call_model", _node_call_model)
_workflow.add_node("exec_tools", _node_exec_tools)
_workflow.add_node("finalize",   _node_finalize)

_workflow.add_edge(START, "call_model")

_workflow.add_conditional_edges(
    "call_model",
    _route,
    {"exec_tools": "exec_tools", "finalize": "finalize"},
)

_workflow.add_edge("exec_tools", "call_model")
_workflow.add_edge("finalize",   END)

_graph = _workflow.compile()


# ---------------------------------------------------------------------------
# Public API — identical signature to loop.py
# ---------------------------------------------------------------------------

def run(
    query: str,
    verbose: bool = False,
    max_iterations: int = MAX_ITERATIONS,
    tracer: Tracer | None = None,
    tools_override: list[dict] | None = None,
) -> Diagnosis:
    """Run the LangGraph agent on a symptom query and return a structured Diagnosis.

    Drop-in replacement for agent.loop.run — same arguments, same return type.
    """
    if tracer:
        tracer.start(query)

    initial_state: _State = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": query},
        ],
        "iteration":      0,
        "max_iterations": max_iterations,
        "verbose":        verbose,
        "tools_override": tools_override,
        "tracer":         tracer,
        "diagnosis":      None,
    }

    final_state = _graph.invoke(initial_state)
    return final_state["diagnosis"]
