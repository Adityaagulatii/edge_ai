"""
Named scenarios for the Edge AI demo.

Two categories:
  - "baseline" : the real BMS screenshot data as-is (shows actual building state)
  - all others : start from a normalized building + add specific fault condition

The screenshot data has several inherent anomalies (undercooled zones, overheated zones).
_CLEAN_OVERRIDES normalizes all of them to setpoint so demo scenarios are unambiguous.

zone_overrides : {VAV-id: {field: value, ...}}  - merged over baseline per-zone
rtu_overrides  : {RTU-id: {field: value, ...}}  - merged over baseline per-RTU
wifi           : int | None  - exact device count (None = random 20-45)
poe            : float | None  - exact watts (None = random 5800-6400)
"""

# All zones that are anomalous OR borderline in the real screenshot.
# Normalized to setpoint so demo scenarios show only the intended fault.
# Borderline = |delta| exactly == EPSILON_DIV (2.0F) - noise makes them flip ~50% of cycles.
_CLEAN_OVERRIDES = {
    "VAV-1":  {"zone_temp": 74},   # screenshot: 70F (-4F undercooled)
    "VAV-2":  {"zone_temp": 74},   # screenshot: 72F (-2F borderline)
    "VAV-3":  {"zone_temp": 74},   # screenshot: 68F (-6F undercooled)
    "VAV-4":  {"zone_temp": 74},   # screenshot: 71F (-3F undercooled)
    "VAV-6":  {"zone_temp": 74},   # screenshot: 78F (+4F overheating)
    "VAV-10": {"zone_temp": 74},   # screenshot: 72F (-2F borderline)
    "VAV-11": {"zone_temp": 74},   # screenshot: 68F (-6F undercooled)
    "VAV-16": {"zone_temp": 74},   # screenshot: 76F (+2F borderline)
    "VAV-17": {"zone_temp": 74},   # screenshot: 76F (+2F borderline)
    "VAV-20": {"zone_temp": 74},   # screenshot: 79F (+5F overheating)
    "VAV-21": {"zone_temp": 74},   # screenshot: 70F (-4F undercooled)
    "VAV-22": {"zone_temp": 71},   # screenshot: 79F (+8F overheating, SP=71)
    "VAV-26": {"zone_temp": 74},   # screenshot: 72F (-2F borderline)
}

# Hubs with permanent No Data zones (VAV-7, VAV-18, VAV-23) have online_ratio < 1.
# With standard random PoE (~6000W), their EFE formula fires false positives.
# Clean scenarios use reduced poe/wifi so EFE doesn't distract from the intended fault.
_CLEAN_POWER = {"wifi": 20, "poe": 5000}

SCENARIOS = {

    # ── Real screenshot - keep as-is ────────────────────────────────────────
    "baseline": {
        "description":       "Real BMS floor plan data - no overrides, real building state",
        "expected_triggers": "Hub-1 critical (VAV-1/3/4 undercooled), Hub-2/3/5 moderate",
        "zone_overrides":    {},
        "rtu_overrides":     {},
        "wifi":              None,
        "poe":               None,
    },

    # ── Clean building - no faults ──────────────────────────────────────────
    "clean_slate": {
        "description":       "All zones normalized to setpoint - Pipeline A only, no Ollama fires",
        "expected_triggers": "none - CVC does not escalate",
        "zone_overrides":    _CLEAN_OVERRIDES,
        "rtu_overrides":     {},
        **_CLEAN_POWER,
    },

    # ── Trigger 1: Single hub moderate overheating (Hub-3) ──────────────────
    "zone_overheat": {
        "description":       "Hub-3 moderate - VAV-12/13 overheating (too warm), hub Ollama auto-fires",
        "expected_triggers": "belief_divergence moderate in Hub-3 only -> Hub-3 auto-adjusts setpoint down",
        "zone_overrides": {
            **_CLEAN_OVERRIDES,
            "VAV-12": {"zone_temp": 78},   # +4F above SP 74 — too warm
            "VAV-13": {"zone_temp": 79},   # +5F above SP 74 — too warm
        },
        "rtu_overrides": {},
        **_CLEAN_POWER,
    },

    # ── Trigger 1: Single hub moderate undercooling (Hub-3) ─────────────────
    "too_cold": {
        "description":       "Hub-3 moderate - VAV-11/12 undercooled (too cold), RTU-10 over-supplying",
        "expected_triggers": "belief_divergence moderate in Hub-3 only -> Hub-3 auto-adjusts setpoint up",
        "zone_overrides": {
            **_CLEAN_OVERRIDES,
            "VAV-11": {"zone_temp": 65},   # -9F below SP 74 — too cold
            "VAV-12": {"zone_temp": 66},   # -8F below SP 74 — too cold
        },
        "rtu_overrides": {},
        **_CLEAN_POWER,
    },

    # ── Trigger 0: Sensor goes offline ──────────────────────────────────────
    "sensor_loss": {
        "description":       "VAV-8 sensor goes offline - Trigger 0 critical, CVC escalates",
        "expected_triggers": "sensor_loss critical in Hub-2 -> CVC Ollama + Telegram B",
        "zone_overrides": {
            **_CLEAN_OVERRIDES,
            "VAV-8": {"zone_temp": None, "setpoint": None,
                      "occ_cool_sp": None, "occ_heat_sp": None},
        },
        "rtu_overrides": {},
        **_CLEAN_POWER,
    },

    # ── Trigger 2: Unexplained power draw ────────────────────────────────────
    "power_surge": {
        "description":       "PoE draw 30% above expected - Trigger 2 EFE error in all hubs",
        "expected_triggers": "efe_error moderate in all hubs -> each hub auto-acts autonomously",
        "zone_overrides":    _CLEAN_OVERRIDES,
        "rtu_overrides":     {},
        "wifi":              30,      # 30 devices -> expected_power = 5000+50*30 = 6500W
        "poe":               8500,    # efe_error = (8500-6500)/6500 = 0.31 -> moderate
    },

    # ── Trigger 1: RTU overcooling ────────────────────────────────────────────
    "rtu_fault": {
        "description":       "RTU-9 discharge drops to 41F - overcooling in Hub-2",
        "expected_triggers": "belief_divergence moderate in Hub-2 -> Hub-2 auto-acts",
        "zone_overrides":    _CLEAN_OVERRIDES,
        "rtu_overrides": {
            "RTU-9": {"discharge_temp": 41},   # below 45F RTU_OVERCOOL_THRESH
        },
        **_CLEAN_POWER,
    },

    # ── Trigger 1: Cross-zone critical (two hubs) ─────────────────────────────
    "multi_hub_crisis": {
        "description":       "Hub-2 + Hub-4 critical overheating - cross-zone, CVC escalates",
        "expected_triggers": "belief_divergence critical (cross-zone) -> CVC Ollama + Telegram A+B",
        "zone_overrides": {
            **_CLEAN_OVERRIDES,
            # Hub-2: 3/4 reportable overheating -> div=0.75 -> critical
            "VAV-6":  {"zone_temp": 82},
            "VAV-8":  {"zone_temp": 81},
            "VAV-10": {"zone_temp": 80},
            # Hub-4: 3/4 reportable overheating -> div=0.75 -> critical
            "VAV-16": {"zone_temp": 80},
            "VAV-19": {"zone_temp": 80},
            "VAV-20": {"zone_temp": 83},
        },
        "rtu_overrides": {},
        **_CLEAN_POWER,
    },

    # ── All three triggers simultaneously ─────────────────────────────────────
    "full_storm": {
        "description":       "All 3 IAIF triggers at once - sensor loss + overheating + RTU fault + power surge",
        "expected_triggers": "sensor_loss + belief_divergence + efe_error -> critical -> full CVC escalation",
        "zone_overrides": {
            **_CLEAN_OVERRIDES,
            "VAV-8":  {"zone_temp": None, "setpoint": None,   # Trigger 0: new No Data
                       "occ_cool_sp": None, "occ_heat_sp": None},
            "VAV-6":  {"zone_temp": 82},                       # Trigger 1: Hub-2 overheating
            "VAV-10": {"zone_temp": 80},
            "VAV-19": {"zone_temp": 80},                       # Trigger 1: Hub-4 overheating
            "VAV-20": {"zone_temp": 83},
        },
        "rtu_overrides": {
            "RTU-9": {"discharge_temp": 41},                   # Trigger 1: RTU fault Hub-2
        },
        "wifi":  30,
        "poe":   9200,                                          # Trigger 2: efe_error ~0.42
    },

    # ── Backward-compat spike ─────────────────────────────────────────────────
    "spike": {
        "description":       "Original spike demo - VAV-6/20/22 extreme overheating + RTU-6 overcooling",
        "expected_triggers": "belief_divergence critical (Hub-2/4/5) + RTU-6 overcooling",
        "zone_overrides": {
            "VAV-6":  {"zone_temp": 81},
            "VAV-20": {"zone_temp": 82},
            "VAV-22": {"zone_temp": 84},
        },
        "rtu_overrides": {
            "RTU-6": {"discharge_temp": 38},
        },
        "wifi":  None,
        "poe":   None,
    },
}

SCENARIO_NAMES = list(SCENARIOS.keys())


def get_scenario(name):
    if name not in SCENARIOS:
        raise KeyError(f"Unknown scenario '{name}'. Available: {SCENARIO_NAMES}")
    return SCENARIOS[name]


def print_scenarios():
    BOLD  = "\033[1m"
    CYAN  = "\033[96m"
    GREEN = "\033[92m"
    RESET = "\033[0m"
    print(f"\n{BOLD}Available scenarios:{RESET}")
    print(f"  {'Name':<20}  Description")
    print("  " + "-" * 70)
    for name, sc in SCENARIOS.items():
        print(f"  {CYAN}{name:<20}{RESET}  {sc['description']}")
        print(f"  {'':20}  {GREEN}Expected: {sc['expected_triggers']}{RESET}")
        print()
