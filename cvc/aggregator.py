import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

_SEVERITY_RANK = {"none": 0, "moderate": 1, "critical": 2}


def merge_zone_reports(reports):
    """Merges 5 hub zone_reports into a single building_state dict."""
    hub_reports       = {r["hub_id"]: r for r in reports}
    all_vav_snapshot  = {}
    all_rtu_snapshot  = {}
    all_anomalies     = []
    all_zones_affected = []
    all_no_data_zones  = []
    critical_hubs      = []
    moderate_hubs      = []
    hub_ollama_failures = []

    worst_severity = "none"
    cycle          = max(r["cycle"] for r in reports)
    timestamp_utc  = max(r["timestamp_utc"] for r in reports)

    for r in reports:
        hub_id   = r["hub_id"]
        sig      = r["signal"]
        severity = sig["severity"]

        all_vav_snapshot.update(r["vav_snapshot"])
        all_rtu_snapshot.update(r["rtu_snapshot"])
        all_anomalies.extend(sig["anomalies"])
        all_zones_affected.extend(sig["zones_affected"])
        all_no_data_zones.extend(sig["no_data_zones"])

        if _SEVERITY_RANK[severity] > _SEVERITY_RANK[worst_severity]:
            worst_severity = severity

        if severity == "critical":
            critical_hubs.append(hub_id)
        elif severity == "moderate":
            moderate_hubs.append(hub_id)

        if not r.get("hub_ollama_ok", True):
            hub_ollama_failures.append(hub_id)

    # Deduplicate
    all_zones_affected = list(dict.fromkeys(all_zones_affected))
    all_no_data_zones  = list(dict.fromkeys(all_no_data_zones))

    cross_zone = is_cross_zone_issue(reports)
    building_div = compute_building_divergence(reports)

    return {
        "cycle":                    cycle,
        "timestamp_utc":            timestamp_utc,
        "hub_reports":              hub_reports,
        "all_vav_snapshot":         all_vav_snapshot,
        "all_rtu_snapshot":         all_rtu_snapshot,
        "building_severity":        worst_severity,
        "building_divergence_score": building_div,
        "critical_hubs":            critical_hubs,
        "moderate_hubs":            moderate_hubs,
        "all_anomalies":            all_anomalies,
        "all_zones_affected":       all_zones_affected,
        "all_no_data_zones":        all_no_data_zones,
        "cross_zone_issue":         cross_zone,
        "hub_ollama_failures":      hub_ollama_failures,
    }


def is_cross_zone_issue(reports):
    """True if anomalous zones appear in >= 2 different hub reports."""
    hubs_with_anomalies = sum(
        1 for r in reports if len(r["signal"]["zones_affected"]) > 0
    )
    return hubs_with_anomalies >= 2


def compute_building_divergence(reports):
    """Weighted average divergence score across hubs, weighted by reportable VAV count."""
    total_weight = 0
    weighted_sum = 0.0
    for r in reports:
        vav_snap     = r["vav_snapshot"]
        n_reportable = sum(1 for d in vav_snap.values() if d["zone_temp"] is not None)
        if n_reportable == 0:
            continue
        weighted_sum  += r["signal"]["divergence_score"] * n_reportable
        total_weight  += n_reportable
    return round(weighted_sum / total_weight, 3) if total_weight else 0.0
