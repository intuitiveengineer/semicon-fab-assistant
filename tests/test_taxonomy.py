"""Consistency tests for the domain taxonomy seed (`scripts/taxonomy.py`).

These enforce the cross-references that were previously only eyeballed in the
module's `__main__` dump: every registry is keyed by its own id, every tool
declares known module/process types, and every alarm/signature points at things
that actually exist — with module scope respected (no etch-only subsystem on a
deposition tool, or vice versa).

Tests are parametrized so a failure names the exact offending tool/alarm/signature.
"""

import pytest

from scripts.taxonomy import (
    ALARMS,
    MODULE_TYPES,
    PROCESS_TYPES,
    SIGNATURES,
    SUBSYSTEMS,
    TOOLS,
)


# --- registries are keyed by their own id -----------------------------------

@pytest.mark.parametrize("tool", TOOLS.values(), ids=lambda t: t.tool_id)
def test_tool_registry_key_matches_id(tool):
    assert TOOLS[tool.tool_id] is tool


@pytest.mark.parametrize("sub", SUBSYSTEMS.values(), ids=lambda s: s.subsystem_id)
def test_subsystem_registry_key_matches_id(sub):
    assert SUBSYSTEMS[sub.subsystem_id] is sub


@pytest.mark.parametrize("alarm", ALARMS.values(), ids=lambda a: a.code)
def test_alarm_registry_key_matches_code(alarm):
    assert ALARMS[alarm.code] is alarm


@pytest.mark.parametrize("sig", SIGNATURES.values(), ids=lambda s: s.signature_id)
def test_signature_registry_key_matches_id(sig):
    assert SIGNATURES[sig.signature_id] is sig


# --- tools declare known module/process types -------------------------------

@pytest.mark.parametrize("tool", TOOLS.values(), ids=lambda t: t.tool_id)
def test_tool_module_and_process_types_known(tool):
    assert tool.module_type in MODULE_TYPES
    assert tool.process_type in PROCESS_TYPES
    assert tool.chambers, f"{tool.tool_id} has no chambers"


# --- subsystem scope is a non-empty subset of module types ------------------

@pytest.mark.parametrize("sub", SUBSYSTEMS.values(), ids=lambda s: s.subsystem_id)
def test_subsystem_applies_to_known_modules(sub):
    assert sub.applies_to, f"{sub.subsystem_id} applies_to is empty"
    assert set(sub.applies_to) <= set(MODULE_TYPES)


# --- alarms reference a real subsystem --------------------------------------

@pytest.mark.parametrize("alarm", ALARMS.values(), ids=lambda a: a.code)
def test_alarm_references_known_subsystem(alarm):
    assert alarm.subsystem in SUBSYSTEMS, (
        f"{alarm.code} references unknown subsystem {alarm.subsystem!r}"
    )


# --- signatures: references resolve -----------------------------------------

@pytest.mark.parametrize("sig", SIGNATURES.values(), ids=lambda s: s.signature_id)
def test_signature_references_resolve(sig):
    assert sig.tools, f"{sig.signature_id} has no tools"
    for tool_id in sig.tools:
        assert tool_id in TOOLS, f"{sig.signature_id}: unknown tool {tool_id!r}"
    assert sig.root_cause_subsystem in SUBSYSTEMS, (
        f"{sig.signature_id}: unknown subsystem {sig.root_cause_subsystem!r}"
    )
    if sig.preceding_alarm is not None:
        assert sig.preceding_alarm in ALARMS, (
            f"{sig.signature_id}: unknown alarm {sig.preceding_alarm!r}"
        )


# --- signatures: module scope is consistent with the tools ------------------

@pytest.mark.parametrize("sig", SIGNATURES.values(), ids=lambda s: s.signature_id)
def test_signature_subsystems_in_scope_for_tools(sig):
    root = SUBSYSTEMS[sig.root_cause_subsystem]
    alarm = ALARMS[sig.preceding_alarm] if sig.preceding_alarm else None
    for tool_id in sig.tools:
        module = TOOLS[tool_id].module_type
        assert module in root.applies_to, (
            f"{sig.signature_id}: root cause {root.subsystem_id} "
            f"not present on {tool_id} ({module})"
        )
        if alarm is not None:
            alarm_sub = SUBSYSTEMS[alarm.subsystem]
            assert module in alarm_sub.applies_to, (
                f"{sig.signature_id}: alarm {alarm.code} ({alarm.subsystem}) "
                f"not present on {tool_id} ({module})"
            )
