import re


def build_hub_prompt(hub_id, vav_snapshot, rtu_snapshot, signal, weather, wifi_count, poe_watts):
    """Builds zone-scoped LLM prompt for moderate-severity IAIF triggers."""
    vav_lines = []
    for zone, d in vav_snapshot.items():
        temp = d["zone_temp"]
        sp   = d["setpoint"]
        if temp is None:
            vav_lines.append(f"  {zone:<8} NO DATA")
        elif sp is not None:
            delta = temp - sp
            sign  = "+" if delta >= 0 else ""
            vav_lines.append(f"  {zone:<8} {temp:.1f}F  SP={sp}F  d={sign}{delta:.1f}F")
        else:
            vav_lines.append(f"  {zone:<8} {temp:.1f}F  SP=--")

    rtu_lines = []
    for rtu, d in rtu_snapshot.items():
        dt = d["discharge_temp"]
        sp = d["discharge_sp"]
        if dt is None:
            rtu_lines.append(f"  {rtu:<8} NO DATA")
        else:
            sp_str = f"{sp}F" if sp is not None else "--"
            rtu_lines.append(f"  {rtu:<8} discharge={dt:.1f}F  SP={sp_str}")

    anomaly_lines = "\n".join(f"  - {a}" for a in signal["anomalies"]) or "  (none)"
    rtu_block     = "\n".join(rtu_lines) or "  (none assigned)"

    system = (
        f"You are an autonomous HVAC controller AI managing {hub_id} in a smart building. "
        "Respond concisely. For each anomalous zone propose a corrective setpoint change. "
        "End your response with one ADJUST line per zone in the exact format:\n"
        "ADJUST: <VAV-ID> <signed_degF>"
    )

    user = f"""[ZONE STATUS - {hub_id}]
Outdoor: {weather.get('temp_f', '--')}F  |  {weather.get('humidity_pct', '--')}% RH  |  {weather.get('wind_mph', '--')}mph wind

VAV Readings:
{chr(10).join(vav_lines)}

RTU Readings:
{rtu_block}

IAIF Trigger: {signal['trigger_type']}  (severity: moderate)
Divergence score: {signal['divergence_score']:.2f}
WiFi devices: {wifi_count}  |  PoE load: {poe_watts:.0f}W

Anomalies:
{anomaly_lines}

Recommend corrective setpoint adjustments for the anomalous zones above. Be specific and brief."""

    return f"SYSTEM:\n{system}\n\nUSER:\n{user}"


def parse_hub_response(llm_text):
    """
    Extracts (recommendation_text, [(zone_id, delta_f), ...]) from LLM response.
    ADJUST lines are stripped from the recommendation text.
    """
    adjust_re  = re.compile(r'^ADJUST:\s+(\S+)\s+([-+]?\d+\.?\d*)', re.MULTILINE)
    adjustments = [(m.group(1), float(m.group(2))) for m in adjust_re.finditer(llm_text)]
    rec_text    = adjust_re.sub("", llm_text).strip()
    return rec_text, adjustments
