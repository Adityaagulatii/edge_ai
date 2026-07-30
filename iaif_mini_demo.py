"""
iaif_mini_demo.py
=================
Self-contained IAIF pipeline demo — no Ollama required.

Run:  python iaif_mini_demo.py
      python iaif_mini_demo.py --live   (uses real Ollama if running)

Shows 3 scenarios side-by-side:
  Splunk Edge Hub (standard) → threshold alert → waits for human
  IAIF on Edge               → detects pattern → auto-corrects setpoint

Each scenario runs the real signal_lookout + prompt_assembly code from this repo.
LLM responses are pre-written for the demo (or live if --live flag passed).
"""

import sys, os, time, textwrap, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
from edge.signal_lookout import check_triggers
from edge.prompt_assembly import build_hub_prompt, parse_hub_response

# ── Terminal colours ──────────────────────────────────────────────────────────
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
SEP    = f"{DIM}{'─'*64}{RESET}"

USE_LIVE_LLM = "--live" in sys.argv

# ── Mock LLM responses for each scenario (used when not --live) ───────────────
_MOCK_LLM = {
    "solar_gain": (
        "VAV-6 is experiencing solar gain from the south-facing glass wall. "
        "Temperature is +7°F above setpoint at 11am — consistent with daily sun pattern. "
        "Recommend pre-emptive cooling. VAV-9 mild overheating, minor adjustment.\n"
        "ADJUST: VAV-6 -3.0\n"
        "ADJUST: VAV-9 -1.0"
    ),
    "server_cold": (
        "VAV-8 and VAV-11 are adjacent to server rooms — persistent cold air bleed is "
        "causing undercooling. This is a physical characteristic, not a fault. "
        "Slight setpoint increase will reduce overcorrection without affecting servers.\n"
        "ADJUST: VAV-8 +2.0\n"
        "ADJUST: VAV-11 +1.5"
    ),
    "multi_hub": (
        "Building-wide overheating in Hub-4 and Hub-5 driven by afternoon sun and rooftop "
        "exposure. Hub-2 server rooms cold. Cross-zone pattern: solar load on south/west "
        "faces. Recommend staging up chiller capacity and pre-cooling south-facing zones.\n"
        "ADJUST: VAV-20 -4.0\n"
        "ADJUST: VAV-22 -3.5\n"
        "ADJUST: VAV-17 -2.0"
    ),
}

# ── Scenario definitions ──────────────────────────────────────────────────────
SCENARIOS = [
    {
        "name":    "Scenario 1 — Solar Gain (Hub-2, South Glass Office)",
        "hub":     "Hub-2",
        "mock_key": "solar_gain",
        "desc":    "VAV-6 (south glass office) overheating at 11am. VAV-9 mild. VAV-7 offline.",
        "vavs": {
            "VAV-6":  {"zone_temp": 81.0, "setpoint": 74.0},
            "VAV-7":  {"zone_temp": None, "setpoint": 74.0},
            "VAV-8":  {"zone_temp": 71.5, "setpoint": 74.0},
            "VAV-9":  {"zone_temp": 77.2, "setpoint": 74.0},
            "VAV-10": {"zone_temp": 73.8, "setpoint": 74.0},
        },
        "rtus": {"RTU-9": {"discharge_temp": 52.0, "discharge_sp": 55.0}},
        "wifi": 42, "poe": 5800,
    },
    {
        "name":    "Scenario 2 — Server Room Cold Bleed (Hub-2 + Hub-3)",
        "hub":     "Hub-2",
        "mock_key": "server_cold",
        "desc":    "VAV-8 and VAV-11 cold due to server room adjacency — persistent physical characteristic.",
        "vavs": {
            "VAV-6":  {"zone_temp": 75.0, "setpoint": 74.0},
            "VAV-7":  {"zone_temp": None, "setpoint": 74.0},
            "VAV-8":  {"zone_temp": 68.2, "setpoint": 74.0},
            "VAV-9":  {"zone_temp": 73.5, "setpoint": 74.0},
            "VAV-10": {"zone_temp": 74.1, "setpoint": 74.0},
        },
        "rtus": {"RTU-9": {"discharge_temp": 54.0, "discharge_sp": 55.0}},
        "wifi": 38, "poe": 5200,
    },
    {
        "name":    "Scenario 3 — Critical Multi-Hub Overheating (Hub-4 + Hub-5)",
        "hub":     "Hub-4",
        "mock_key": "multi_hub",
        "desc":    "Hub-4 penthouse + Hub-5 rooftop corner — afternoon solar load across south/west faces.",
        "vavs": {
            "VAV-16": {"zone_temp": 78.5, "setpoint": 74.0},
            "VAV-17": {"zone_temp": 80.2, "setpoint": 74.0},
            "VAV-18": {"zone_temp": None, "setpoint": 74.0},
            "VAV-19": {"zone_temp": 73.0, "setpoint": 74.0},
            "VAV-20": {"zone_temp": 84.0, "setpoint": 74.0},
        },
        "rtus": {"RTU-11": {"discharge_temp": 42.0, "discharge_sp": 55.0}},
        "wifi": 61, "poe": 7100,
    },
]

WEATHER = {"temp_f": 91.0, "humidity_pct": 68, "wind_mph": 6}


# ── Helpers ───────────────────────────────────────────────────────────────────
def pause(t=0.6):
    time.sleep(t)

def header(text, col=CYAN):
    print(f"\n{col}{BOLD}{'━'*64}{RESET}")
    print(f"{col}{BOLD}  {text}{RESET}")
    print(f"{col}{BOLD}{'━'*64}{RESET}")

def step(label, col=YELLOW):
    print(f"\n{col}{BOLD}▶ {label}{RESET}")

def sensor_table(hub, vavs, rtus):
    print(f"  {DIM}{'Zone':<10} {'Temp':>7}  {'SP':>5}  {'Δ':>7}  Status{RESET}")
    print(f"  {DIM}{'----':<10} {'----':>7}  {'--':>5}  {'--':>7}  ------{RESET}")
    for z, d in vavs.items():
        t, sp = d["zone_temp"], d["setpoint"]
        if t is None:
            print(f"  {DIM}{z:<10} {'NO DATA':>7}  offline{RESET}")
        else:
            delta = t - sp
            col = RED if delta > 2 else (BLUE if delta < -2 else GREEN)
            flag = " ◄ OVER" if delta > 2 else (" ◄ COLD" if delta < -2 else "")
            print(f"  {col}{z:<10} {t:>6.1f}°F  {sp:>4.0f}°F  {delta:>+6.1f}°F{flag}{RESET}")
    for rtu, d in rtus.items():
        dt = d["discharge_temp"]
        flag = f"  {RED}◄ OVERCOOLING{RESET}" if dt < 45 else ""
        print(f"  {DIM}{rtu:<10} discharge={dt:.1f}°F{RESET}{flag}")

def splunk_response(signal):
    sev = signal["severity"]
    div = signal["divergence_score"]
    col = RED if sev == "critical" else (YELLOW if sev == "moderate" else GREEN)
    print(f"\n  {DIM}┌─ SPLUNK EDGE HUB (standard threshold behaviour) ─────────┐{RESET}")
    print(f"  {DIM}│{RESET}  Divergence score: {col}{div:.2f}{RESET}")
    print(f"  {DIM}│{RESET}  Severity: {col}{BOLD}{sev.upper()}{RESET}")
    if signal["anomalies"]:
        for a in signal["anomalies"][:3]:
            print(f"  {DIM}│{RESET}    • {a}")
    print(f"  {DIM}│{RESET}")
    if sev == "none":
        print(f"  {DIM}│{RESET}  {GREEN}→ No threshold breached. No action.{RESET}")
    else:
        print(f"  {DIM}│{RESET}  {YELLOW}→ Threshold alert fired → email sent to engineer{RESET}")
        print(f"  {DIM}│{RESET}  {DIM}→ Waiting for human to log in and investigate...{RESET}")
        print(f"  {DIM}│{RESET}  {DIM}→ Mean time to response: 15–45 minutes{RESET}")
    print(f"  {DIM}└──────────────────────────────────────────────────────────┘{RESET}")

def iaif_response(hub, vavs, rtus, signal, mock_key):
    sev = signal["severity"]
    div = signal["divergence_score"]
    col = RED if sev == "critical" else (YELLOW if sev == "moderate" else GREEN)

    print(f"\n  {CYAN}┌─ IAIF on Edge (local LLM decision loop) ─────────────────┐{RESET}")
    print(f"  {CYAN}│{RESET}  Divergence score: {col}{div:.2f}{RESET}  →  Trigger: {signal['trigger_type'] or 'none'}")

    if sev == "none":
        print(f"  {CYAN}│{RESET}  {GREEN}→ Below thresholds. No LLM invoked. Monitoring.{RESET}")
        print(f"  {CYAN}└──────────────────────────────────────────────────────────┘{RESET}")
        return

    print(f"  {CYAN}│{RESET}  Severity: {col}{BOLD}{sev.upper()}{RESET}  →  {CYAN}Querying local Ollama LLM...{RESET}")
    pause(0.4)

    prompt = build_hub_prompt(hub, vavs, rtus, signal, WEATHER, 40, 5500)

    if USE_LIVE_LLM:
        from edge.ollama_client import query_ollama
        import config
        print(f"  {CYAN}│{RESET}  {DIM}[live] sending to {config.HUB_OLLAMA_URL}...{RESET}")
        result = query_ollama(prompt, config.HUB_MODEL, config.HUB_OLLAMA_URL, timeout=30)
        if result["ok"]:
            llm_text = result["text"]
            elapsed  = result["elapsed_sec"]
        else:
            print(f"  {CYAN}│{RESET}  {RED}Ollama unavailable ({result['error']}) — using mock response{RESET}")
            llm_text = _MOCK_LLM[mock_key]
            elapsed  = 0.0
    else:
        pause(0.8)
        llm_text = _MOCK_LLM[mock_key]
        elapsed  = 1.4

    rec_text, adjustments = parse_hub_response(llm_text)
    print(f"  {CYAN}│{RESET}")
    print(f"  {CYAN}│{RESET}  {BOLD}LLM reasoning ({elapsed:.1f}s):{RESET}")
    for line in textwrap.wrap(rec_text, 54):
        print(f"  {CYAN}│{RESET}    {line}")

    if adjustments:
        print(f"  {CYAN}│{RESET}")
        print(f"  {CYAN}│{RESET}  {BOLD}Auto setpoint corrections applied:{RESET}")
        for zone, delta in adjustments:
            orig_sp = vavs.get(zone, {}).get("setpoint", 74.0)
            new_sp  = round(orig_sp + delta, 1)
            col2    = RED if delta > 0 else BLUE
            print(f"  {CYAN}│{RESET}    {GREEN}✓{RESET} {zone:<8}  {orig_sp:.0f}°F → {new_sp:.1f}°F  ({col2}{delta:+.1f}°F{RESET})")
        pause(0.3)
        print(f"  {CYAN}│{RESET}")
        print(f"  {CYAN}│{RESET}  {GREEN}→ Correction sent via BACnet. No human needed.{RESET}")
        print(f"  {CYAN}│{RESET}  {GREEN}→ Next cycle will verify temperatures recovered.{RESET}")
    print(f"  {CYAN}└──────────────────────────────────────────────────────────┘{RESET}")


def comparison_summary():
    header("COMPARISON SUMMARY", BOLD)
    rows = [
        ("Detect anomaly",        f"{GREEN}✓ immediate{RESET}",    f"{GREEN}✓ immediate{RESET}"),
        ("Understand root cause", f"{RED}✗ threshold only{RESET}", f"{GREEN}✓ LLM reasoning{RESET}"),
        ("Auto-correct setpoint", f"{RED}✗ waits for human{RESET}",f"{GREEN}✓ applies in <2s{RESET}"),
        ("Cross-hub awareness",   f"{RED}✗{RESET}",                f"{GREEN}✓ CVC aggregation{RESET}"),
        ("Distinguish solar/fault",f"{RED}✗ same alert{RESET}",    f"{GREEN}✓ context-aware{RESET}"),
        ("Time to correction",    f"{YELLOW}15–45 min{RESET}",     f"{GREEN}< 15 seconds{RESET}"),
        ("Works offline",         f"{YELLOW}partial{RESET}",       f"{GREEN}✓ fully local{RESET}"),
        ("Audit trail",           f"{GREEN}✓ Splunk index{RESET}", f"{GREEN}✓ logs/events.jsonl{RESET}"),
    ]
    col_w = 26
    print(f"\n  {BOLD}{'Capability':<{col_w}} {'Splunk Edge (standard)':<28} {'IAIF on Edge'}{RESET}")
    print(f"  {'─'*col_w}  {'─'*28}  {'─'*22}")
    for cap, splunk, iaif in rows:
        print(f"  {cap:<{col_w}}  {splunk:<38}  {iaif}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    mode = f"{CYAN}LIVE Ollama{RESET}" if USE_LIVE_LLM else f"{YELLOW}Mock LLM responses{RESET}"
    header(f"IAIF Mini Pipeline Demo  [{mode}]")
    print(f"""
  Demonstrates the Intelligent Autonomous Infrastructure Framework (IAIF)
  running on a Splunk Edge Hub to manage HVAC in a Boston office building.

  Each scenario shows the SAME sensor data processed two ways:
    {YELLOW}Splunk Edge Hub (standard){RESET} — threshold rules + human response
    {CYAN}IAIF on Edge{RESET}               — local LLM + automatic correction

  Setpoint: 74°F  |  Comfort band: ±2°F  |  Building: 26 VAVs / 5 Hubs
  {DIM}Run with --live to use real Ollama (llama3.2 must be pulled){RESET}
""")
    pause(1.0)

    for i, sc in enumerate(SCENARIOS, 1):
        header(f"[{i}/3]  {sc['name']}")
        print(f"\n  {DIM}{sc['desc']}{RESET}\n")
        pause(0.5)

        step("Sensor readings from BMS (via BACnet/Modbus → Edge Hub)")
        sensor_table(sc["hub"], sc["vavs"], sc["rtus"])
        pause(0.6)

        signal = check_triggers(
            sc["vavs"], sc["rtus"], sc["wifi"], sc["poe"],
            previous_snapshot=None, no_data_streak={}
        )

        step("Splunk Edge Hub — standard threshold processing")
        splunk_response(signal)
        pause(0.8)

        step("IAIF — intelligent edge processing")
        iaif_response(sc["hub"], sc["vavs"], sc["rtus"], signal, sc["mock_key"])
        pause(1.0)

        if i < len(SCENARIOS):
            print(f"\n{DIM}  Press Enter for next scenario (or wait 3s)...{RESET}", end="", flush=True)
            try:
                import select
                if select.select([sys.stdin], [], [], 3)[0]:
                    sys.stdin.readline()
            except Exception:
                pause(3)

    comparison_summary()
    print(f"  {DIM}Full system: python main.py   |   Dashboard: python generate_html_report.py{RESET}\n")


if __name__ == "__main__":
    main()
