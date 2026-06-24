"""Agent v0 — plain Python tool-calling loop.

Takes a symptom query, calls tools until it has enough evidence, then
returns a structured Diagnosis. No framework — just the OpenAI API primitives
so the loop mechanics are fully visible.

Usage:
    from agent.loop import run
    diagnosis = run("ETCH02 showing etch-rate drift and across-wafer non-uniformity")
"""

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config  # noqa: E402  triggers load_dotenv + key validation
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


def run(
    query: str,
    verbose: bool = False,
    max_iterations: int = MAX_ITERATIONS,
    tracer: Tracer | None = None,
    tools_override: list[dict] | None = None,
) -> Diagnosis:
    """Run the agent loop on a symptom query and return a structured Diagnosis.

    Args:
        query:          Natural-language symptom description.
        verbose:        If True, print each tool call and result to stdout.
        max_iterations: Hard cap on tool-call rounds before forcing final answer.
        tracer:         Optional Tracer instance; caller must call tracer.save().
        tools_override: If provided, use these tool schemas instead of the default
                        TOOLS list (used by the eval harness for ablations).

    Returns:
        A validated Diagnosis object.
    """
    active_tools = tools_override if tools_override is not None else TOOLS

    if tracer:
        tracer.start(query)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": query},
    ]

    for iteration in range(max_iterations):
        response = _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=active_tools,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        # Build the assistant turn as a plain dict for the messages list.
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
        messages.append(assistant_turn)

        # No tool calls → LLM is done gathering evidence.
        if not msg.tool_calls:
            if verbose:
                print(f"[loop] iteration {iteration + 1}: LLM finished tool calls")
            if tracer:
                tracer.record_iteration(iteration + 1)
            break

        # Execute each tool call and append the result.
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            if verbose:
                print(f"[tool] {tc.function.name}({args})")

            t0 = time.time()
            result = dispatch(tc.function.name, args)
            latency_ms = int((time.time() - t0) * 1000)

            if verbose:
                preview = json.dumps(result)[:200]
                print(f"       → {preview}")

            if tracer:
                tracer.record_tool_call(tc.function.name, args, result, latency_ms)

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(result),
            })

    else:
        # Iteration cap reached — log and proceed to structured output anyway.
        if verbose:
            print(f"[loop] hit max_iterations={max_iterations}, forcing final answer")
        if tracer:
            tracer.record_iteration(max_iterations)

    # Final call: extract the structured Diagnosis from the accumulated conversation.
    # We use beta.chat.completions.parse which handles the JSON schema negotiation
    # with the API and returns a validated Pydantic object directly.
    final = _client.beta.chat.completions.parse(
        model=MODEL,
        messages=messages,
        response_format=Diagnosis,
    )

    diagnosis = final.choices[0].message.parsed

    if tracer:
        tracer.finish(diagnosis, final.usage)

    return diagnosis
