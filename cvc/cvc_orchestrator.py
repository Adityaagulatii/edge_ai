import sys
import os
import queue
import time
import threading
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from cvc.aggregator import merge_zone_reports
from cvc.cvc_prompt import build_cvc_prompt, parse_cvc_response
from edge.ollama_client import query_ollama
from controller.telegram_bot import send_pipeline_a, send_pipeline_b
from controller.splunk_logger import log_event
from data_sources.weather_api import get_weather

BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"

_SEVERITY_RANK = {"none": 0, "moderate": 1, "critical": 2}


def run_cvc(cvc_queue, num_hubs, scenario=None, stop_event=None):
    """CVC daemon thread. Collects hub reports, aggregates, escalates if needed."""
    cycle   = 0
    weather = get_weather(config.WEATHER_LAT, config.WEATHER_LON)
    sc_name = scenario.get("_name", "baseline") if scenario else "baseline"

    print(f"\n{BOLD}[CVC]{RESET} Central Visualization/Control started  "
          f"scenario={sc_name}  (waiting for {num_hubs} hubs)\n")

    while stop_event is None or not stop_event.is_set():
        reports = _collect_hub_reports(cvc_queue, num_hubs, config.HUB_REPORT_TIMEOUT)
        if not reports:
            continue
        cycle += 1

        if cycle % 10 == 1:
            weather = get_weather(config.WEATHER_LAT, config.WEATHER_LON)

        building_state = merge_zone_reports(reports)
        _print_building_dashboard(building_state, cycle)

        cvc_action = None
        if _should_escalate_to_cvc(building_state):
            prompt = build_cvc_prompt(building_state, weather)
            _print_cvc_prompt(cycle, prompt)
            log_event("cvc_prompt", "cvc", {"cycle": cycle, "prompt": prompt})

            result = query_ollama(prompt, config.CVC_MODEL, config.CVC_OLLAMA_URL, timeout=60)

            if result["ok"]:
                rec_text, action_code = parse_cvc_response(result["text"])
                _print_cvc_response(cycle, result["text"], result["elapsed_sec"], action_code)
                log_event("cvc_llm_response", "cvc", {
                    "cycle": cycle, "response": result["text"],
                    "action_code": action_code, "elapsed_sec": result["elapsed_sec"],
                })

                if action_code in ("URGENT", "SHUTDOWN"):
                    ok_a = send_pipeline_a(building_state, rec_text)
                    ok_b = send_pipeline_b(building_state, rec_text)
                    print(f"  Telegram Pipeline A: {'SENT' if ok_a else 'skipped (no token)'}  "
                          f"Pipeline B: {'SENT' if ok_b else 'skipped (no token)'}")
                elif action_code == "MONITOR":
                    ok_a = send_pipeline_a(building_state, rec_text)
                    print(f"  Telegram Pipeline A: {'SENT' if ok_a else 'skipped (no token)'}")

                cvc_action = {"action_code": action_code, "recommendation": rec_text,
                              "elapsed_sec": result["elapsed_sec"]}
                log_event("cvc_action", "cvc",
                          {"cycle": cycle, "action_code": action_code,
                           "building_severity": building_state["building_severity"]})
            else:
                print(f"\n{RED}[CVC]{RESET} Ollama FAILED: {result['error']} - sending raw alert")
                send_pipeline_b(building_state, "CVC AI OFFLINE - manual review required")
                log_event("ollama_failure", "cvc", {"cycle": cycle, "error": result["error"]})
        else:
            log_event("hub_report", "cvc",
                      {"cycle": cycle, "building_severity": building_state["building_severity"],
                       "building_divergence_score": building_state["building_divergence_score"]})


def _print_cvc_prompt(cycle, prompt):
    print(f"\n{YELLOW}[CVC] {'='*50}{RESET}")
    print(f"{BOLD}[CVC] PROMPT TO OLLAMA  cycle={cycle}{RESET}")
    for line in prompt.splitlines():
        print(f"[CVC]   {line}")
    print(f"{YELLOW}[CVC] {'='*50}{RESET}")


def _print_cvc_response(cycle, text, elapsed, action_code):
    col = RED if action_code in ("URGENT", "SHUTDOWN") else YELLOW
    print(f"\n{col}[CVC] {'='*50}{RESET}")
    print(f"{BOLD}[CVC] OLLAMA RESPONSE  cycle={cycle}  ({elapsed:.1f}s)  ACTION:{action_code}{RESET}")
    for line in text.strip().splitlines():
        print(f"[CVC]   {line}")
    print(f"{col}[CVC] {'='*50}{RESET}\n")


def _should_escalate_to_cvc(building_state):
    """Returns True if CVC LLM should be invoked this cycle."""
    bs = building_state
    if _SEVERITY_RANK[bs["building_severity"]] >= _SEVERITY_RANK["critical"]:
        return True
    if bs["cross_zone_issue"]:
        return True
    if len(bs["hub_ollama_failures"]) >= 2:
        return True
    if bs["building_divergence_score"] > config.DIV_THRESHOLD_CRIT:
        return True
    return False


def _collect_hub_reports(cvc_queue, num_hubs, timeout):
    """Drains exactly num_hubs items from cvc_queue within total timeout seconds."""
    per_hub_timeout = max(timeout / num_hubs, 2.0)
    reports = []
    for _ in range(num_hubs):
        try:
            report = cvc_queue.get(timeout=per_hub_timeout)
            reports.append(report)
        except queue.Empty:
            pass   # Hub missed the deadline - skipped (not a stub; aggregator handles partial)
    return reports


def _print_building_dashboard(building_state, cycle):
    bs       = building_state
    severity = bs["building_severity"]
    sev_col  = RED if severity == "critical" else (YELLOW if severity == "moderate" else GREEN)

    print(f"\n{BOLD}[CVC] {'='*50}{RESET}")
    print(f"{BOLD}[CVC] Building Dashboard - Cycle {cycle}  "
          f"{sev_col}{severity.upper()}{RESET}")
    print(f"[CVC]   Divergence: {bs['building_divergence_score']:.2f}  "
          f"Cross-zone: {'YES' if bs['cross_zone_issue'] else 'no'}  "
          f"Hubs: {len(bs['hub_reports'])}/5")
    if bs["critical_hubs"]:
        print(f"[CVC]   {RED}Critical: {', '.join(bs['critical_hubs'])}{RESET}")
    if bs["moderate_hubs"]:
        print(f"[CVC]   {YELLOW}Moderate: {', '.join(bs['moderate_hubs'])}{RESET}")
    if bs["all_no_data_zones"]:
        print(f"[CVC]   No Data: {', '.join(bs['all_no_data_zones'])}")
    for hub_id, report in bs["hub_reports"].items():
        sig = report["signal"]
        act = report.get("hub_action")
        act_str = f"  auto-adj: {act['zones_adjusted']}" if act else ""
        sev = sig["severity"]
        col = RED if sev == "critical" else (YELLOW if sev == "moderate" else GREEN)
        print(f"[CVC]   {col}{hub_id}{RESET}: {sev:<8} div={sig['divergence_score']:.2f}{act_str}")
    print(f"{BOLD}[CVC] {'='*50}{RESET}\n")
