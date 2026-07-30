import sys
import os
import time
import threading
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from data_sources.bms_floor_plan import get_hub_snapshot
from data_sources.cisco_wifi_mock import get_wifi_count
from data_sources.poe_switch_mock import get_poe_consumption
from data_sources.weather_api import get_weather
from edge.signal_lookout import check_triggers
from edge.prompt_assembly import build_hub_prompt, parse_hub_response
from edge.ollama_client import query_ollama
from controller.splunk_logger import log_event

BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
RED   = "\033[91m"
RESET = "\033[0m"


def run_hub(hub_id, cvc_queue, scenario=None, stop_event=None):
    """Per-hub daemon thread. Collects zone data, runs IAIF, reports to CVC."""
    cycle          = 0
    no_data_streak = {}
    prev_snapshot  = None
    weather        = get_weather(config.WEATHER_LAT, config.WEATHER_LON)

    sc_name = scenario.get("_name", "baseline") if scenario else "baseline"
    print(f"{BOLD}[{hub_id}]{RESET} started  scenario={sc_name}  zones={config.ZONE_MAP[hub_id]['vavs']}")

    while stop_event is None or not stop_event.is_set():
        cycle += 1
        ts = datetime.now(timezone.utc).isoformat()

        hub_snap = get_hub_snapshot(hub_id, scenario=scenario)
        vav_snap = hub_snap["vavs"]
        rtu_snap = hub_snap["rtus"]

        # Use scenario wifi/poe overrides if present, else random mock
        wifi_override = scenario.get("wifi") if scenario else None
        poe_override  = scenario.get("poe")  if scenario else None
        wifi = wifi_override if wifi_override is not None else get_wifi_count()
        poe  = poe_override  if poe_override  is not None else get_poe_consumption()

        # Refresh weather every 10 cycles to avoid hammering the API
        if cycle % 10 == 1:
            weather = get_weather(config.WEATHER_LAT, config.WEATHER_LON)

        signal = check_triggers(
            vav_snap, rtu_snap, wifi, poe,
            previous_snapshot=prev_snapshot,
            no_data_streak=no_data_streak,
        )
        no_data_streak = signal["updated_no_data_streak"]
        prev_snapshot  = vav_snap

        hub_action    = None
        hub_ollama_ok = True

        severity = signal["severity"]

        if severity == "moderate":
            _print_sensor_table(hub_id, cycle, vav_snap, rtu_snap, wifi, poe, signal)
            prompt = build_hub_prompt(hub_id, vav_snap, rtu_snap, signal, weather, wifi, poe)
            _print_prompt_block(hub_id, cycle, prompt)
            log_event("hub_sensor_data", hub_id, {
                "cycle": cycle, "vav_snapshot": vav_snap,
                "rtu_snapshot": rtu_snap, "wifi": wifi, "poe": poe,
            })
            log_event("hub_prompt", hub_id, {"cycle": cycle, "prompt": prompt})

            result = query_ollama(prompt, config.HUB_MODEL, config.HUB_OLLAMA_URL, timeout=30)
            hub_ollama_ok = result["ok"]

            if result["ok"]:
                _print_llm_response(hub_id, cycle, result["text"], result["elapsed_sec"])
                log_event("hub_llm_response", hub_id, {
                    "cycle": cycle, "response": result["text"],
                    "elapsed_sec": result["elapsed_sec"],
                })
                rec_text, adjustments = parse_hub_response(result["text"])
                zones_adj, delta = _apply_setpoint_adjustment(hub_id, vav_snap, adjustments)
                hub_action = {
                    "recommendation": rec_text,
                    "setpoint_delta": delta,
                    "zones_adjusted": zones_adj,
                    "elapsed_sec":    result["elapsed_sec"],
                }
                log_event("hub_action", hub_id, {"cycle": cycle, "hub_action": hub_action})
                sev_col = YELLOW
            else:
                print(f"{RED}[{hub_id}] Ollama FAILED: {result['error']}{RESET}")
                log_event("ollama_failure", hub_id, {"cycle": cycle, "error": result["error"]})
                sev_col = YELLOW
        elif severity == "critical":
            _print_sensor_table(hub_id, cycle, vav_snap, rtu_snap, wifi, poe, signal)
            log_event("hub_sensor_data", hub_id, {
                "cycle": cycle, "vav_snapshot": vav_snap,
                "rtu_snapshot": rtu_snap, "wifi": wifi, "poe": poe,
            })
            sev_col = RED
            hub_ollama_ok = True
        else:
            sev_col = GREEN

        _print_hub_status(hub_id, cycle, severity, signal, hub_action, sev_col)

        zone_report = {
            "hub_id":        hub_id,
            "cycle":         cycle,
            "timestamp_utc": ts,
            "vav_snapshot":  vav_snap,
            "rtu_snapshot":  rtu_snap,
            "signal":        {k: v for k, v in signal.items() if k != "updated_no_data_streak"},
            "hub_action":    hub_action,
            "hub_ollama_ok": hub_ollama_ok,
        }

        log_event("hub_report", hub_id, {"cycle": cycle, "severity": severity})
        cvc_queue.put(zone_report)

        if stop_event is not None:
            stop_event.wait(timeout=config.POLL_INTERVAL)
        else:
            time.sleep(config.POLL_INTERVAL)


def _apply_setpoint_adjustment(hub_id, vav_snapshot, adjustments):
    """Applies ADJUST commands from LLM. Clamps delta to [-5, +5] degF."""
    zones_adjusted = []
    net_delta      = 0.0
    for zone_id, raw_delta in adjustments:
        if zone_id not in vav_snapshot:
            continue
        delta = max(-5.0, min(5.0, raw_delta))
        zones_adjusted.append(zone_id)
        net_delta = delta
        sp = vav_snapshot[zone_id].get("setpoint")
        new_sp = round(sp + delta, 1) if sp is not None else None
        print(f"  {CYAN}[{hub_id}] ADJUST {zone_id}: setpoint {sp}F -> {new_sp}F (d={delta:+.1f}F){RESET}")
    return zones_adjusted, net_delta


def _print_sensor_table(hub_id, cycle, vav_snap, rtu_snap, wifi, poe, signal):
    P = f"[{hub_id}]"
    print(f"\n{CYAN}{P} {'-'*50}{RESET}")
    print(f"{BOLD}{P} SENSOR INPUT  cycle={cycle}{RESET}")
    print(f"{P}   {'Zone':<8} {'Temp':>7}  {'Setpoint':>9}  {'Delta':>7}  Status")
    print(f"{P}   {'----':<8} {'----':>7}  {'--------':>9}  {'-----':>7}  ------")
    for z, d in vav_snap.items():
        temp = d["zone_temp"]
        sp   = d["setpoint"]
        if temp is None:
            print(f"{P}   {z:<8} {'NO DATA':>7}  offline")
        elif sp is not None:
            delta = temp - sp
            flag  = " <<" if abs(delta) >= 2.0 else ""
            print(f"{P}   {z:<8} {temp:>6.1f}F  {sp:>7}F SP  {delta:>+6.1f}F{flag}")
        else:
            print(f"{P}   {z:<8} {temp:>6.1f}F  SP=--")
    for rtu, d in rtu_snap.items():
        dt = d["discharge_temp"]
        sp = d.get("discharge_sp")
        if dt is None:
            print(f"{P}   {rtu:<8} RTU offline")
        else:
            sp_str = f"{sp}F SP" if sp else "--"
            flag   = " << OVERCOOL" if dt is not None and dt < 45 else ""
            print(f"{P}   {rtu:<8} discharge={dt:.1f}F  {sp_str}{flag}")
    print(f"{P}   WiFi: {wifi}  PoE: {poe:.0f}W  Trigger: {signal['trigger_type']}  div={signal['divergence_score']:.2f}")
    print(f"{CYAN}{P} {'-'*50}{RESET}")


def _print_prompt_block(hub_id, cycle, prompt):
    P = f"[{hub_id}]"
    print(f"\n{YELLOW}{P} {'-'*50}{RESET}")
    print(f"{BOLD}{P} PROMPT TO OLLAMA  cycle={cycle}{RESET}")
    for line in prompt.splitlines():
        print(f"{P}   {line}")
    print(f"{YELLOW}{P} {'-'*50}{RESET}")


def _print_llm_response(hub_id, cycle, text, elapsed):
    P = f"[{hub_id}]"
    print(f"\n{GREEN}{P} {'-'*50}{RESET}")
    print(f"{BOLD}{P} OLLAMA RESPONSE  cycle={cycle}  ({elapsed:.1f}s){RESET}")
    for line in text.strip().splitlines():
        print(f"{P}   {line}")
    print(f"{GREEN}{P} {'-'*50}{RESET}\n")


def _print_hub_status(hub_id, cycle, severity, signal, hub_action, sev_col):
    tag = f"{sev_col}[{severity.upper()}]{RESET}" if severity != "none" else f"{GREEN}[OK]{RESET}"
    print(f"{BOLD}[{hub_id}]{RESET} cycle={cycle} {tag} "
          f"div={signal['divergence_score']:.2f}  "
          f"anomalies={len(signal['anomalies'])}", end="")
    if hub_action:
        adj = hub_action['zones_adjusted']
        print(f"  -> auto-adjusted {adj} ({hub_action['elapsed_sec']:.1f}s)", end="")
    print()
