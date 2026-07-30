import re


def build_cvc_prompt(building_state, weather):
    """Builds building-level LLM prompt for critical or cross-zone escalation."""
    bs = building_state

    # Per-hub anomaly block (only hubs with issues)
    hub_lines = []
    for hub_id, report in bs["hub_reports"].items():
        sig = report["signal"]
        if sig["severity"] == "none":
            continue
        action_taken = "YES" if report.get("hub_action") else "NO"
        hub_lines.append(
            f"  {hub_id}: severity={sig['severity']}  "
            f"div={sig['divergence_score']:.2f}  "
            f"hub_acted={action_taken}\n"
            f"    anomalies: {'; '.join(sig['anomalies']) or 'none'}"
        )

    hub_block       = "\n".join(hub_lines) or "  (all hubs normal)"
    anomaly_summary = "\n".join(f"  - {a}" for a in bs["all_anomalies"]) or "  (none)"
    no_data_str     = ", ".join(bs["all_no_data_zones"]) or "none"
    cross_str       = "YES" if bs["cross_zone_issue"] else "NO"
    fail_str        = ", ".join(bs["hub_ollama_failures"]) or "none"

    system = (
        "You are a building-level HVAC AI with full visibility across all 5 zones. "
        "A zone-level AI has already attempted to handle moderate anomalies. "
        "You are assessing a situation requiring building-level response. "
        "Diagnose the root cause, classify urgency, and recommend a course of action. "
        "End your response with exactly one line:\n"
        "ACTION: <URGENT|MONITOR|SHUTDOWN>"
    )

    user = f"""[BUILDING STATE - Cycle {bs['cycle']}]
Outdoor: {weather.get('temp_f','--')}F  |  {weather.get('humidity_pct','--')}% RH  |  {weather.get('wind_mph','--')}mph wind

Building divergence score : {bs['building_divergence_score']:.2f}
Building severity         : {bs['building_severity'].upper()}
Cross-zone issue detected : {cross_str}
Critical hubs             : {', '.join(bs['critical_hubs']) or 'none'}
Moderate hubs             : {', '.join(bs['moderate_hubs']) or 'none'}
Hub Ollama failures       : {fail_str}

Per-hub anomaly summary:
{hub_block}

All anomalous zones: {', '.join(bs['all_zones_affected']) or 'none'}
Sensor losses      : {no_data_str}

All anomalies detected:
{anomaly_summary}

Provide a building-level diagnosis. Classify urgency as:
  URGENT   - dispatch engineer immediately
  MONITOR  - watch next cycle, no immediate action
  SHUTDOWN - shut down affected RTU(s) for safety"""

    return f"SYSTEM:\n{system}\n\nUSER:\n{user}"


def parse_cvc_response(llm_text):
    """Returns (recommendation_text, action_code) from CVC LLM response."""
    match = re.search(r'^ACTION:\s+(URGENT|MONITOR|SHUTDOWN)', llm_text, re.MULTILINE)
    action_code = match.group(1) if match else "UNKNOWN"
    rec_text    = re.sub(r'^ACTION:\s+\S+\s*$', '', llm_text, flags=re.MULTILINE).strip()
    return rec_text, action_code
