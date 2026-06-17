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
  2. Subsystems (shared functional vocabulary).
  3. Alarm/fault code catalog.   <-- you are here
Still to come: failure signatures.
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


@dataclass(frozen=True)
class AlarmCode:
    """A fault/alarm code the equipment can emit.

    Each code belongs to exactly one subsystem (by id) so the agent's
    `lookup_alarm_code` tool, the event-log documents, and the failure signatures
    all agree on what a code means. Hardware-only subsystems (rf_cabling,
    gas_injector, edge_ring, foreline) raise no codes here — they show up as root
    causes in the failure signatures (a later task), not as alarms.
    """

    code: str                        # flat id, e.g. "ALM-001" (subsystem is a field, not in the id)
    text: str                        # short operator-facing description
    subsystem: str                   # a SUBSYSTEMS id this alarm belongs to
    typical_causes: tuple[str, ...]  # plain-language likely causes (feeds diagnosis later)


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


# Alarm/fault code catalog, keyed by code. Flat ALM-### ids; the owning subsystem
# is a field (not encoded in the id). Hardware-only subsystems (rf_cabling,
# gas_injector, edge_ring, foreline) intentionally have no codes here — they are
# root causes in the failure signatures, not self-reporting alarms.
ALARMS: dict[str, AlarmCode] = {
    alarm.code: alarm
    for alarm in (
        # --- rf_source ---
        AlarmCode("ALM-001", "RF power failed to reach setpoint", "rf_source",
                  ("RF generator fault", "degraded RF cabling", "match unable to tune")),
        AlarmCode("ALM-002", "Plasma failed to ignite", "rf_source",
                  ("incorrect gas/pressure conditions", "RF generator fault", "match network fault")),
        AlarmCode("ALM-003", "RF generator over-temperature", "rf_source",
                  ("cooling water flow low", "prolonged high-power operation", "generator cooling fault")),
        AlarmCode("ALM-004", "Arc detected", "rf_source",
                  ("chamber contamination/particles", "damaged RF cabling", "process instability")),
        # --- rf_match ---
        AlarmCode("ALM-005", "High reflected power", "rf_match",
                  ("match failed to tune", "degraded RF cabling", "plasma/impedance instability")),
        AlarmCode("ALM-006", "Match failed to tune (auto-tune timeout)", "rf_match",
                  ("vacuum capacitor motor fault", "out-of-range load impedance", "controller fault")),
        AlarmCode("ALM-007", "Match position/capacitor out of range", "rf_match",
                  ("vacuum capacitor wear", "calibration drift", "motor/encoder fault")),
        # --- gas_box ---
        AlarmCode("ALM-008", "MFC flow failed to reach setpoint", "gas_box",
                  ("MFC fault", "upstream supply pressure low", "clogged/failed valve")),
        AlarmCode("ALM-009", "MFC flow deviation/drift", "gas_box",
                  ("MFC drift/aging", "contamination in MFC", "calibration overdue")),
        AlarmCode("ALM-010", "Gas supply pressure low", "gas_box",
                  ("depleted gas source", "regulator fault", "line leak")),
        AlarmCode("ALM-011", "MFC zero/offset fault", "gas_box",
                  ("MFC zero drift", "trapped gas during zero", "sensor fault")),
        AlarmCode("ALM-012", "Isolation valve failed to open/close", "gas_box",
                  ("pneumatic supply fault", "valve actuator failure", "stuck valve")),
        # --- rough_pump ---
        AlarmCode("ALM-013", "Roughing pressure failed to reach setpoint", "rough_pump",
                  ("rough pump degradation", "foreline leak", "throttle valve stuck")),
        AlarmCode("ALM-014", "Pump not running / fault", "rough_pump",
                  ("pump motor failure", "power/interlock fault", "seized pump")),
        AlarmCode("ALM-015", "Pump over-temperature", "rough_pump",
                  ("cooling fault", "ballast/load too high", "worn pump")),
        AlarmCode("ALM-016", "Exhaust pressure high", "rough_pump",
                  ("abatement backpressure", "clogged exhaust line", "downstream restriction")),
        # --- turbo_pump ---
        AlarmCode("ALM-017", "Failed to reach base pressure", "turbo_pump",
                  ("vacuum leak", "turbo degradation", "outgassing/contamination")),
        AlarmCode("ALM-018", "Turbo not at speed", "turbo_pump",
                  ("turbo controller fault", "foreline pressure too high", "bearing wear")),
        AlarmCode("ALM-019", "Turbo over-temperature", "turbo_pump",
                  ("cooling water flow low", "high gas load", "bearing degradation")),
        AlarmCode("ALM-020", "Turbo vibration/bearing fault", "turbo_pump",
                  ("bearing wear", "rotor imbalance", "particle ingress")),
        AlarmCode("ALM-021", "Turbo controller fault", "turbo_pump",
                  ("controller hardware fault", "communication loss", "power supply fault")),
        # --- throttle_valve ---
        AlarmCode("ALM-022", "Chamber pressure control fault (cannot hold setpoint)", "throttle_valve",
                  ("stuck throttle valve", "capacitance manometer fault", "pumping speed change")),
        AlarmCode("ALM-023", "Valve stuck / position fault", "throttle_valve",
                  ("mechanical seizure/particles", "actuator fault", "encoder fault")),
        AlarmCode("ALM-024", "Valve calibration fault", "throttle_valve",
                  ("calibration drift", "manometer mismatch", "controller fault")),
        # --- abatement ---
        AlarmCode("ALM-025", "High backpressure", "abatement",
                  ("clogged abatement inlet", "byproduct buildup", "downstream restriction")),
        AlarmCode("ALM-026", "Combustor failed to ignite", "abatement",
                  ("igniter fault", "fuel gas supply low", "flame sensor fault")),
        AlarmCode("ALM-027", "Abatement offline / not ready (processing blocked)", "abatement",
                  ("abatement fault/alarm", "maintenance state", "utility supply loss")),
        AlarmCode("ALM-028", "Scrubber water flow low", "abatement",
                  ("water supply fault", "clogged nozzle/line", "pump fault")),
        AlarmCode("ALM-029", "Abatement over-temperature", "abatement",
                  ("cooling fault", "excessive load", "water flow low")),
        # --- wafer_handling ---
        AlarmCode("ALM-030", "Wafer slip during transfer", "wafer_handling",
                  ("end-effector wear/contamination", "excessive acceleration", "vacuum/grip loss")),
        AlarmCode("ALM-031", "Wafer path/position deviation", "wafer_handling",
                  ("robot calibration drift", "obstruction", "encoder fault")),
        AlarmCode("ALM-032", "Robot motion fault/timeout", "wafer_handling",
                  ("motor/encoder fault", "obstruction/interlock", "controller fault")),
        AlarmCode("ALM-033", "Slit valve failed open/close", "wafer_handling",
                  ("pneumatic supply fault", "particle obstruction", "actuator failure")),
        AlarmCode("ALM-034", "Wafer present/absent sensor mismatch", "wafer_handling",
                  ("sensor fault", "misplaced wafer", "broken wafer")),
        AlarmCode("ALM-035", "Aligner/pre-aligner fault", "wafer_handling",
                  ("aligner sensor fault", "notch/flat not found", "rotation motor fault")),
        # --- esc (etch) ---
        AlarmCode("ALM-036", "Chuck failed to reach temperature", "esc",
                  ("chiller not at setpoint", "ESC heater fault", "He backside flow loss")),
        AlarmCode("ALM-037", "Clamp/dechuck fault", "esc",
                  ("ESC HV supply fault", "residual charge", "backside contamination")),
        AlarmCode("ALM-038", "He backside cooling leak", "esc",
                  ("wafer backside seal leak", "cracked wafer", "ESC surface wear")),
        # --- chiller (etch) ---
        AlarmCode("ALM-039", "Coolant not at setpoint (too warm)", "chiller",
                  ("compressor fault", "low coolant level", "high heat load")),
        AlarmCode("ALM-040", "Coolant flow low", "chiller",
                  ("pump fault", "clogged filter/line", "coolant leak")),
        AlarmCode("ALM-041", "Coolant leak detected", "chiller",
                  ("hose/fitting leak", "ESC/line crack", "level sensor")),
        AlarmCode("ALM-042", "Compressor / over-temperature fault", "chiller",
                  ("compressor failure", "condenser airflow blocked", "refrigerant fault")),
        # --- bias_rf_source (etch) ---
        AlarmCode("ALM-043", "Bias power failed to reach setpoint", "bias_rf_source",
                  ("bias generator fault", "degraded RF cabling", "bias match unable to tune")),
        AlarmCode("ALM-044", "Bias arc detected", "bias_rf_source",
                  ("chamber contamination/particles", "wafer/ESC arcing", "damaged cabling")),
        # --- bias_rf_match (etch) ---
        AlarmCode("ALM-045", "High reflected power (bias)", "bias_rf_match",
                  ("bias match failed to tune", "degraded RF cabling", "impedance instability")),
        AlarmCode("ALM-046", "Bias match failed to tune", "bias_rf_match",
                  ("vacuum capacitor motor fault", "out-of-range impedance", "controller fault")),
        # --- endpoint_detection (etch) ---
        AlarmCode("ALM-047", "Failed to reach/find endpoint", "endpoint_detection",
                  ("incorrect film/recipe", "weak emission signal", "fouled optical window")),
        AlarmCode("ALM-048", "Endpoint signal low / window fouled", "endpoint_detection",
                  ("optical window deposition/fouling", "detector fault", "light source degradation")),
        # --- heater_pedestal (deposition) ---
        AlarmCode("ALM-049", "Pedestal failed to reach temperature", "heater_pedestal",
                  ("heater element fault", "thermocouple fault", "power controller fault")),
        AlarmCode("ALM-050", "Pedestal over-temperature", "heater_pedestal",
                  ("temperature controller fault", "thermocouple drift", "runaway heater")),
        AlarmCode("ALM-051", "Zone temperature non-uniformity", "heater_pedestal",
                  ("heater zone degradation", "thermocouple drift", "pedestal wear")),
        AlarmCode("ALM-052", "Thermocouple fault", "heater_pedestal",
                  ("thermocouple open/short", "connector fault", "wiring damage")),
        # --- precursor_delivery (deposition) ---
        AlarmCode("ALM-053", "Heated-line temperature low (condensation risk)", "precursor_delivery",
                  ("heater/jacket fault", "controller fault", "ambient heat loss")),
        AlarmCode("ALM-054", "Ampoule level low/empty", "precursor_delivery",
                  ("precursor depletion", "level sensor fault", "draw faster than refill")),
        AlarmCode("ALM-055", "Precursor pressure/flow deviation", "precursor_delivery",
                  ("ampoule temperature off", "clogged line/valve", "carrier flow deviation")),
        AlarmCode("ALM-056", "Vaporizer fault", "precursor_delivery",
                  ("vaporizer heater fault", "clogging", "controller fault")),
        AlarmCode("ALM-057", "Carrier gas flow fault", "precursor_delivery",
                  ("MFC fault", "supply pressure low", "valve fault")),
        # --- remote_plasma (deposition) ---
        AlarmCode("ALM-058", "Remote plasma failed to ignite", "remote_plasma",
                  ("clean gas supply issue", "RPS source fault", "pressure out of range")),
        AlarmCode("ALM-059", "Remote plasma source over-temperature", "remote_plasma",
                  ("cooling fault", "prolonged operation", "high power")),
        AlarmCode("ALM-060", "Chamber-clean endpoint not reached", "remote_plasma",
                  ("incomplete clean/heavy deposition", "endpoint detector fault", "RPS power low")),
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
    print(f"  {len(SUBSYSTEMS)} subsystems total\n")

    print("ALARMS")
    for alarm in ALARMS.values():
        print(f"  {alarm.code:8} {alarm.subsystem:20} {alarm.text}")
    print(f"  {len(ALARMS)} alarms total")

    # Light sanity check: every alarm must reference a real subsystem id.
    bad_refs = sorted(a.code for a in ALARMS.values() if a.subsystem not in SUBSYSTEMS)
    print(f"\n  alarm -> subsystem refs valid: {not bad_refs}"
          + (f"  (bad: {bad_refs})" if bad_refs else ""))
