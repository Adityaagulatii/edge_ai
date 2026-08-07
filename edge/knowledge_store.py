"""
knowledge_store.py  —  IAIF Agentic Learning Layer
====================================================
Closes the autonomous learning loop for the IAIF pipeline.

Without this:  LLM makes the same decision every cycle with no memory.
With this:     LLM sees what worked before and adapts its reasoning.

Flow:
  Cycle N:   Signal Lookout fires → Prompt Assembly injects past context
             → LLM reasons with history → correction applied
             → record_correction() stores the attempt

  Cycle N+1: verify_outcome() checks if temp recovered
             → marks attempt SUCCESS or FAILED
             → future prompts include: "Last time VAV-6 solar gain,
               -3°F worked in 2 cycles"

Storage:  logs/knowledge_store.jsonl  (one JSON line per event)
Retrieval: retrieve_context() returns top-K relevant past learnings
           ranked by recency + success rate for that zone/trigger pair
"""

import json
import os
import datetime

_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "knowledge_store.jsonl")
_PENDING     = {}   # {(hub_id, zone): pending_record} waiting for outcome verification


def record_correction(hub_id, zone, trigger_type, delta_applied, temp_before, setpoint):
    """
    Store a correction attempt immediately after the LLM applies it.
    Outcome (SUCCESS/FAILED) is filled in by verify_outcome() next cycle.

    Args:
        hub_id       : e.g. "Hub-2"
        zone         : e.g. "VAV-6"
        trigger_type : "belief_divergence" | "sensor_loss" | "efe_error"
        delta_applied: signed float, e.g. -3.0 (°F change to setpoint)
        temp_before  : actual zone temperature before correction
        setpoint     : original setpoint
    """
    record = {
        "ts":           datetime.datetime.utcnow().isoformat(),
        "hub_id":       hub_id,
        "zone":         zone,
        "trigger_type": trigger_type,
        "delta_applied": delta_applied,
        "temp_before":  temp_before,
        "setpoint":     setpoint,
        "deviation":    round(temp_before - setpoint, 2),
        "outcome":      "pending",
        "temp_after":   None,
        "cycles_to_recover": None,
    }
    _PENDING[(hub_id, zone)] = record
    _append(record)


def verify_outcome(hub_id, zone, temp_after, setpoint, tolerance=2.0):
    """
    Called the cycle after a correction. Checks if temperature recovered.
    Updates the stored record with outcome = SUCCESS | FAILED.

    Args:
        temp_after : current zone temperature this cycle
        tolerance  : °F band around setpoint to count as recovered (default ±2°F)
    """
    key = (hub_id, zone)
    if key not in _PENDING:
        return

    record = _PENDING.pop(key)
    recovered = abs(temp_after - setpoint) <= tolerance
    record["outcome"]   = "SUCCESS" if recovered else "FAILED"
    record["temp_after"] = round(temp_after, 2)
    record["cycles_to_recover"] = 1 if recovered else None

    # Rewrite the pending record as a completed outcome record
    _append({**record, "_type": "outcome"})


def retrieve_context(hub_id, trigger_type, zone=None, limit=5):
    """
    Retrieves relevant past learnings to inject into the next LLM prompt.
    Ranked by: exact zone match > same hub > same trigger type, then recency.

    Returns a formatted string ready to append to the LLM prompt, e.g.:
        [Past learnings for Hub-2 / belief_divergence]
        - VAV-6: delta -3.0°F → SUCCESS (recovered in 1 cycle) [2026-08-05]
        - VAV-9: delta -1.0°F → SUCCESS                        [2026-08-05]
        - VAV-6: delta -2.0°F → FAILED (temp stayed +5°F)      [2026-08-03]
    """
    records = _load_completed()

    # Score relevance: exact zone = 3, same hub = 2, same trigger = 1
    def score(r):
        s = 0
        if r.get("hub_id") == hub_id:       s += 2
        if r.get("trigger_type") == trigger_type: s += 1
        if zone and r.get("zone") == zone:  s += 3
        return s

    ranked = sorted(
        [r for r in records if score(r) > 0],
        key=lambda r: (score(r), r.get("ts", "")),
        reverse=True,
    )[:limit]

    if not ranked:
        return ""

    lines = [f"[Past learnings — {hub_id} / {trigger_type}]"]
    for r in ranked:
        outcome  = r.get("outcome", "?")
        delta    = r.get("delta_applied", 0)
        z        = r.get("zone", "?")
        dev      = r.get("deviation", 0)
        date     = r.get("ts", "")[:10]
        suffix   = "(recovered)" if outcome == "SUCCESS" else "(did not recover)"
        lines.append(f"  - {z}: {dev:+.1f}°F deviation → applied {delta:+.1f}°F → {outcome} {suffix} [{date}]")

    return "\n".join(lines)


def success_rate(hub_id, zone, trigger_type):
    """
    Returns (successes, attempts) for a specific zone + trigger pattern.
    Used to decide confidence level before auto-applying vs escalating.
    """
    records = _load_completed()
    relevant = [
        r for r in records
        if r.get("hub_id") == hub_id
        and r.get("zone") == zone
        and r.get("trigger_type") == trigger_type
        and r.get("outcome") in ("SUCCESS", "FAILED")
    ]
    successes = sum(1 for r in relevant if r["outcome"] == "SUCCESS")
    return successes, len(relevant)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _append(record):
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    with open(_STORE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _load_completed():
    if not os.path.exists(_STORE_PATH):
        return []
    records = []
    with open(_STORE_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("outcome") in ("SUCCESS", "FAILED"):
                    records.append(r)
            except json.JSONDecodeError:
                pass
    return records
