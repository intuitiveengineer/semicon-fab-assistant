"""Domain taxonomy for the Semiconductor Maintenance Agent (etch + deposition only).

This module is the **single source of truth** for the fab's vocabulary: the exact
tool IDs, chambers, subsystems, alarm codes, and known failure signatures that every
other part of the system agrees on.

Why it lives in one file:
- *Cross-document consistency* — the data generator samples from here, so "ETCH02"
  means the same tool in a work order, an alarm log, and a tool summary.
- *Ground truth for evaluation* — the planted failure signatures are the answers the
  benchmark grades against.
- *A validation gate* — generated docs that reference a tool/code not defined here are
  rejected, keeping the synthetic corpus honest.

Built incrementally, one reviewable task per section. This file currently covers:
  1. Tool types/IDs and their chambers.
  2. Subsystems (shared functional vocabulary).   <-- you are here
Still to come: the alarm/fault code catalog, and failure signatures.
"""

from __future__ import annotations

from dataclasses import dataclass

# The two equipment families this project is scoped to. Nothing outside these
# (no CMP, litho, implant, metrology) belongs in the taxonomy.
MODULE_TYPES: tuple[str, ...] = ("etch", "deposition")

# Process technologies within those families. Used later to validate that every
# tool declares a known process type.
PROCESS_TYPES: tuple[str, ...] = ("RIE", "plasma_etch", "PECVD", "CVD", "ALD", "PVD")


@dataclass(frozen=True)
class Tool:
    """A single piece of process equipment in the fab.

    Frozen (immutable) on purpose: this is seed data and must never be mutated at
    runtime. Constructing a Tool forces every field to be supplied, so a missing or
    misspelled attribute fails right here instead of silently returning nothing
    deep inside the data generator.
    """

    tool_id: str                # canonical id, e.g. "ETCH02"
    module_type: str            # one of MODULE_TYPES
    process_type: str           # one of PROCESS_TYPES
    chambers: tuple[str, ...]   # chamber/station names local to this tool, e.g. ("PM1", "PM2")

    def chamber_ids(self) -> tuple[str, ...]:
        """Fully-qualified chamber ids, e.g. ("ETCH02_PM1", "ETCH02_PM2", ...).

        This is the form used in document metadata and citations, so we derive it
        from structured data rather than hand-typing every combination.
        """
        return tuple(f"{self.tool_id}_{name}" for name in self.chambers)


@dataclass(frozen=True)
class Subsystem:
    """A functional subsystem shared across tools (RF, vacuum, gas, thermal, ...).

    Subsystems are the connective tissue of the taxonomy: failure signatures (a
    later task) point symptom -> subsystem -> root cause, so they need stable ids.

    `applies_to` records which module families actually have this subsystem, so an
    etch-only subsystem (e.g. the bias RF generator) is never attributed to a
    deposition tool. It defaults to *both* families for the many shared ones.

    Caveat: `applies_to` is coarse (module-type level), so the deposition-only
    subsystems attach to every deposition tool including PVD — which in reality
    doesn't use precursors / remote-plasma clean. We keep PVD minimal for v1 and
    rely on the hand-authored failure signatures to stay tool-accurate.
    """

    subsystem_id: str                           # canonical id, e.g. "rf_match"
    name: str                                   # human-readable label
    applies_to: tuple[str, ...] = MODULE_TYPES  # families that have it; defaults to both


# The fab's equipment roster, keyed by tool_id for O(1) lookup.
# Etch tools use process-module chambers (PM#); the PECVD cluster uses stations
# (STN#) to mirror real deposition-tool naming — the variety is deliberate so the
# corpus doesn't look templated.
TOOLS: dict[str, Tool] = {
    tool.tool_id: tool
    for tool in (
        # --- Etch (RIE / plasma etch) ---
        Tool("ETCH01", "etch", "RIE", ("PM1", "PM2", "PM3")),
        Tool("ETCH02", "etch", "RIE", ("PM1", "PM2", "PM3")),
        Tool("ETCH03", "etch", "plasma_etch", ("PM1", "PM2")),
        # --- Deposition (PECVD / CVD / ALD / PVD) ---
        Tool("PECVD01", "deposition", "PECVD", ("STNA", "STNB", "STNC")),
        Tool("CVD02", "deposition", "CVD", ("PM1", "PM2")),
        Tool("ALD01", "deposition", "ALD", ("PM1", "PM2")),
        Tool("PVD01", "deposition", "PVD", ("PM1", "PM2")),
    )
}


# Scope shorthands for subsystems that aren't shared by both families.
ETCH_ONLY: tuple[str, ...] = ("etch",)
DEP_ONLY: tuple[str, ...] = ("deposition",)

# Functional subsystems, keyed by subsystem_id. Most are common to both families
# (default applies_to); a few are specific to etch (bias RF, ESC cooling, optical
# endpoint) or deposition (heated pedestal, precursor delivery, remote-plasma clean).
SUBSYSTEMS: dict[str, Subsystem] = {
    sub.subsystem_id: sub
    for sub in (
        # --- Common to etch & deposition ---
        Subsystem("rf_source", "Source RF generator (power supply)"),
        Subsystem("rf_match", "RF matcher / match network"),
        Subsystem("rf_cabling", "RF cabling (fixed length; can fail -> RF issues)"),
        Subsystem("gas_box", "Gas box - MFCs and flow meters"),
        Subsystem("gas_injector", "Gas injector / showerhead to chamber"),
        Subsystem("edge_ring", "Edge ring (consumable, PM-scheduled)"),
        Subsystem("rough_pump", "Rough / backing pump"),
        Subsystem("turbo_pump", "Turbomolecular pump"),
        Subsystem("foreline", "Foreline"),
        Subsystem("throttle_valve", "Throttle valve (pressure control)"),
        Subsystem("abatement", "Abatement system"),
        Subsystem("wafer_handling", "Wafer handling (robot, slit valve)"),
        # --- Etch only ---
        Subsystem("esc", "Electrostatic chuck (ESC)", ETCH_ONLY),
        Subsystem("chiller", "Chiller (ESC temperature control)", ETCH_ONLY),
        Subsystem("bias_rf_source", "Bias RF generator", ETCH_ONLY),
        Subsystem("bias_rf_match", "Bias RF matcher", ETCH_ONLY),
        Subsystem("endpoint_detection", "Optical endpoint detection (EPD)", ETCH_ONLY),
        # --- Deposition only ---
        Subsystem("heater_pedestal", "Heated pedestal / susceptor (+ temp control)", DEP_ONLY),
        Subsystem("precursor_delivery", "Precursor delivery (ampoule/bubbler/vaporizer + heated lines)", DEP_ONLY),
        Subsystem("remote_plasma", "Remote plasma source (chamber clean)", DEP_ONLY),
    )
}


if __name__ == "__main__":
    # Human-readable dump so we can eyeball the seed at a glance.
    print("TOOLS")
    for tool in TOOLS.values():
        print(
            f"  {tool.tool_id:9} {tool.module_type:11} {tool.process_type:11} "
            f"{', '.join(tool.chamber_ids())}"
        )
    print(f"  {len(TOOLS)} tools total\n")

    print("SUBSYSTEMS")
    for sub in SUBSYSTEMS.values():
        scope = "both" if sub.applies_to == MODULE_TYPES else "/".join(sub.applies_to)
        print(f"  {sub.subsystem_id:20} {scope:11} {sub.name}")
    print(f"  {len(SUBSYSTEMS)} subsystems total")
