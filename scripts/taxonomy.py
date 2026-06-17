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
  1. Tool types/IDs and their chambers.   <-- you are here
Still to come: subsystems, the alarm/fault code catalog, and failure signatures.
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


if __name__ == "__main__":
    # Human-readable dump so we can eyeball the seed at a glance.
    for tool in TOOLS.values():
        print(
            f"{tool.tool_id:9} {tool.module_type:11} {tool.process_type:11} "
            f"{', '.join(tool.chamber_ids())}"
        )
    print(f"\n{len(TOOLS)} tools total")
