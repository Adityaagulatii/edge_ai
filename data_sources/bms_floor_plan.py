import random

# VAV zone data from FloorPlanPointWrite BMS screenshot
# {zone_id: {zone_temp, setpoint, occ_cool_sp, occ_heat_sp}}
# None values = "No Data" as shown on the floor plan
FLOOR_PLAN_DATA = {
    "VAV-1":  {"zone_temp": 70, "setpoint": 74, "occ_cool_sp": 80, "occ_heat_sp": 73},
    "VAV-2":  {"zone_temp": 72, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
    "VAV-3":  {"zone_temp": 68, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 73},
    "VAV-4":  {"zone_temp": 71, "setpoint": 74, "occ_cool_sp": 80, "occ_heat_sp": 73},
    "VAV-5":  {"zone_temp": 74, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 60},
    "VAV-6":  {"zone_temp": 78, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 60},
    "VAV-7":  {"zone_temp": None, "setpoint": None, "occ_cool_sp": None, "occ_heat_sp": None},
    "VAV-8":  {"zone_temp": 75, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
    "VAV-9":  {"zone_temp": 73, "setpoint": 72, "occ_cool_sp": 74, "occ_heat_sp": 73},
    "VAV-10": {"zone_temp": 72, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
    "VAV-11": {"zone_temp": 68, "setpoint": 74, "occ_cool_sp": 75, "occ_heat_sp": 74},
    "VAV-12": {"zone_temp": 73, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
    "VAV-13": {"zone_temp": 73, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 60},
    "VAV-14": {"zone_temp": 75, "setpoint": 74, "occ_cool_sp": 73, "occ_heat_sp": 74},
    "VAV-15": {"zone_temp": 74, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
    "VAV-16": {"zone_temp": 76, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
    "VAV-17": {"zone_temp": 76, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 71},
    "VAV-18": {"zone_temp": None, "setpoint": None, "occ_cool_sp": None, "occ_heat_sp": None},
    "VAV-19": {"zone_temp": 73, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 60},
    "VAV-20": {"zone_temp": 79, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 72},
    "VAV-21": {"zone_temp": 70, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 73},
    "VAV-22": {"zone_temp": 79, "setpoint": 71, "occ_cool_sp": 75, "occ_heat_sp": 74},
    "VAV-23": {"zone_temp": None, "setpoint": None, "occ_cool_sp": None, "occ_heat_sp": None},
    "VAV-24": {"zone_temp": 74, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
    "VAV-25": {"zone_temp": 74, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
    "VAV-26": {"zone_temp": 72, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 74},
}

RTU_DATA = {
    "RTU-6":  {"discharge_temp": 48, "discharge_sp": 74},
    "RTU-9":  {"discharge_temp": 53, "discharge_sp": 72},
    "RTU-10": {"discharge_temp": 50, "discharge_sp": None},
    "RTU-11": {"discharge_temp": None, "discharge_sp": None},
}

# Spike values for demo — trigger IAI deliberately
_SPIKE_ZONES = {
    "VAV-6":  {"zone_temp": 81, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 60},
    "VAV-20": {"zone_temp": 82, "setpoint": 74, "occ_cool_sp": 74, "occ_heat_sp": 72},
    "VAV-22": {"zone_temp": 84, "setpoint": 71, "occ_cool_sp": 75, "occ_heat_sp": 74},
}
_SPIKE_RTUS = {
    "RTU-6": {"discharge_temp": 38, "discharge_sp": 74},
}


def _add_noise(value, sigma=0.5):
    if value is None:
        return None
    return round(value + random.gauss(0, sigma), 1)


def get_zone_snapshot(spike=False):
    snapshot = {}
    for zone, data in FLOOR_PLAN_DATA.items():
        if spike and zone in _SPIKE_ZONES:
            base = _SPIKE_ZONES[zone]
        else:
            base = data
        snapshot[zone] = {
            "zone_temp":    _add_noise(base["zone_temp"]),
            "setpoint":     base["setpoint"],
            "occ_cool_sp":  base["occ_cool_sp"],
            "occ_heat_sp":  base["occ_heat_sp"],
        }
    return snapshot


def get_rtu_snapshot(spike=False):
    snapshot = {}
    for rtu, data in RTU_DATA.items():
        if spike and rtu in _SPIKE_RTUS:
            base = _SPIKE_RTUS[rtu]
        else:
            base = data
        snapshot[rtu] = {
            "discharge_temp": _add_noise(base["discharge_temp"]),
            "discharge_sp":   base["discharge_sp"],
        }
    return snapshot


def get_hub_snapshot(hub_id, spike=False, scenario=None):
    """
    Returns {"vavs": {...}, "rtus": {...}} for this hub's devices.
    scenario: dict from scenarios.SCENARIOS (takes priority over spike)
    spike:    backward-compat shortcut for scenarios["spike"]
    """
    import config
    zone_overrides = {}
    rtu_overrides  = {}

    if scenario is not None:
        zone_overrides = scenario.get("zone_overrides", {})
        rtu_overrides  = scenario.get("rtu_overrides", {})
    elif spike:
        zone_overrides = _SPIKE_ZONES
        rtu_overrides  = _SPIKE_RTUS

    zone_vavs = config.ZONE_MAP[hub_id]["vavs"]
    zone_rtus = config.ZONE_MAP[hub_id]["rtus"]

    vav_snap = {}
    for z in zone_vavs:
        if z not in FLOOR_PLAN_DATA:
            continue
        base = {**FLOOR_PLAN_DATA[z], **zone_overrides.get(z, {})}
        vav_snap[z] = {
            "zone_temp":   _add_noise(base["zone_temp"]),
            "setpoint":    base["setpoint"],
            "occ_cool_sp": base["occ_cool_sp"],
            "occ_heat_sp": base["occ_heat_sp"],
        }

    rtu_snap = {}
    for r in zone_rtus:
        if r not in RTU_DATA:
            continue
        base = {**RTU_DATA[r], **rtu_overrides.get(r, {})}
        rtu_snap[r] = {
            "discharge_temp": _add_noise(base["discharge_temp"]),
            "discharge_sp":   base["discharge_sp"],
        }

    return {"vavs": vav_snap, "rtus": rtu_snap}
