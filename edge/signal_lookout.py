"""
IAIF Signal Lookout — Trigger classification for Intermittent Active Inference.

Trigger 0 - Sensor Loss       : new No Data zone detected  -> critical
Trigger 1 - Belief Divergence : zone temps vs setpoints    -> moderate / critical
Trigger 2 - EFE Error         : actual vs expected power   -> moderate
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


def check_triggers(zone_snapshot, rtu_snapshot, wifi_count, poe_watts,
                   previous_snapshot=None, no_data_streak=None):
    if no_data_streak is None:
        no_data_streak = {}

    anomalies      = []
    zones_affected = set()
    triggers_fired = []

    all_zones        = list(zone_snapshot.keys())
    no_data_zones    = [z for z in all_zones if zone_snapshot[z]["zone_temp"] is None]
    reportable_zones = [z for z in all_zones if zone_snapshot[z]["zone_temp"] is not None]

    # Update no-data streak counters and detect new No Data zones in one pass
    updated_streak    = {}
    new_no_data_zones = []
    for z in all_zones:
        if zone_snapshot[z]["zone_temp"] is None:
            updated_streak[z] = no_data_streak.get(z, 0) + 1
            if previous_snapshot is not None and previous_snapshot.get(z, {}).get("zone_temp") is not None:
                new_no_data_zones.append(z)
                anomalies.append(f"{z}: sensor went offline this cycle")
        else:
            updated_streak[z] = 0

    persistent_no_data = [z for z in no_data_zones if updated_streak.get(z, 0) >= config.NO_DATA_ESCALATE_CYCLES]

    # Trigger 0: Sensor Loss
    if new_no_data_zones:
        triggers_fired.append("sensor_loss")
        zones_affected.update(new_no_data_zones)

    # Trigger 1: Belief Divergence
    n_overheating = 0
    n_undercooled = 0
    rtu_anomalies = []

    for zone in reportable_zones:
        d   = zone_snapshot[zone]
        sp  = d["setpoint"]
        if sp is None:
            continue
        delta = d["zone_temp"] - sp
        if delta > config.EPSILON_DIV:
            n_overheating += 1
            zones_affected.add(zone)
            anomalies.append(f"{zone}: {d['zone_temp']:.1f}F (SP {sp}F, d=+{delta:.1f}F) OVERHEATING")
        elif delta < -config.EPSILON_DIV:
            n_undercooled += 1
            zones_affected.add(zone)
            anomalies.append(f"{zone}: {d['zone_temp']:.1f}F (SP {sp}F, d={delta:.1f}F) UNDERCOOLED")

    n_report         = len(reportable_zones) if reportable_zones else 1
    divergence_score = round((n_overheating + n_undercooled) / n_report, 3)

    for rtu, d in rtu_snapshot.items():
        dt = d["discharge_temp"]
        if dt is not None and dt < config.RTU_OVERCOOL_THRESH:
            rtu_anomalies.append(rtu)
            zones_affected.add(rtu)
            anomalies.append(f"{rtu}: discharge {dt:.1f}F OVERCOOLING (threshold {config.RTU_OVERCOOL_THRESH}F)")

    if divergence_score > config.DIV_THRESHOLD_MOD or rtu_anomalies:
        triggers_fired.append("belief_divergence")

    # Trigger 2: EFE Error
    online_ratio   = len(reportable_zones) / len(all_zones) if all_zones else 1.0
    expected_power = (config.BASE_WATTS + config.WATTS_PER_DEVICE * wifi_count) * online_ratio
    efe_error      = round((poe_watts - expected_power) / expected_power, 3) if expected_power else 0.0

    if efe_error > config.EFE_THRESHOLD:
        triggers_fired.append("efe_error")
        anomalies.append(
            f"Power anomaly: {poe_watts:.0f}W actual vs {expected_power:.0f}W expected "
            f"({efe_error*100:.1f}% over)"
        )

    signal_detected = len(triggers_fired) > 0
    severity = "none"
    if signal_detected:
        if "sensor_loss" in triggers_fired or divergence_score > config.DIV_THRESHOLD_CRIT:
            severity = "critical"
        else:
            severity = "moderate"

    if len(triggers_fired) == 0:
        trigger_type = None
    elif len(triggers_fired) == 1:
        trigger_type = triggers_fired[0]
    else:
        trigger_type = "combined"

    return {
        "signal_detected":         signal_detected,
        "severity":                severity,
        "trigger_type":            trigger_type,
        "anomalies":               anomalies,
        "zones_affected":          list(zones_affected),
        "no_data_zones":           no_data_zones,
        "new_no_data_zones":       new_no_data_zones,
        "persistent_no_data":      persistent_no_data,
        "divergence_score":        divergence_score,
        "efe_error":               efe_error,
        "updated_no_data_streak":  updated_streak,
    }
