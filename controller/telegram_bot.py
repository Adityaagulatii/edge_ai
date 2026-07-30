import sys
import os
import json
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from controller.splunk_logger import log_event

_API_BASE  = "https://api.telegram.org/bot{token}/{method}"
_BOLD      = "\033[1m"
_CYAN      = "\033[96m"
_RED       = "\033[91m"
_YELLOW    = "\033[93m"
_RESET     = "\033[0m"


def send_pipeline_a(building_state, recommendation):
    """Pipeline A: Engineer status summary (IoT Engineer chat)."""
    bs  = building_state
    top = "\n".join(f"  - {a}" for a in bs["all_anomalies"][:8]) or "  (none)"
    if len(bs["all_anomalies"]) > 8:
        top += f"\n  ... and {len(bs['all_anomalies'])-8} more"

    text = (
        f"*[EDGE AI - Building Status | Cycle {bs['cycle']}]*\n"
        f"Severity: *{bs['building_severity'].upper()}*  |  "
        f"Cross-zone: {'Yes' if bs['cross_zone_issue'] else 'No'}\n"
        f"Critical hubs: {', '.join(bs['critical_hubs']) or 'none'}\n"
        f"Divergence: {bs['building_divergence_score']:.2f}  |  "
        f"Zones affected: {', '.join(bs['all_zones_affected']) or 'none'}\n\n"
        f"*AI Recommendation:*\n{recommendation[:600]}\n\n"
        f"*Top Anomalies:*\n{top}"
    )
    _print_telegram_message("A", "IoT Engineer", bs["cycle"], text)
    log_event("telegram_message", "telegram",
              {"pipeline": "A", "recipient": "IoT Engineer",
               "cycle": bs["cycle"], "message_text": text})
    ok = _send_message(config.TELEGRAM_ENGINEER_CHAT_ID, text)
    log_event("telegram_sent", "telegram", {"pipeline": "A", "cycle": bs["cycle"], "ok": ok})
    return ok


def send_pipeline_b(building_state, recommendation):
    """Pipeline B: Critical alert to Building Operator with inline buttons."""
    bs = building_state
    text = (
        f"*[CRITICAL ALERT | Cycle {bs['cycle']}]*\n"
        f"Building severity: *{bs['building_severity'].upper()}*\n"
        f"Hubs: {', '.join(bs['critical_hubs'] + bs['moderate_hubs'])}\n"
        f"Zones affected: {', '.join(bs['all_zones_affected'][:10]) or 'none'}\n\n"
        f"*CVC Recommendation:*\n{recommendation[:500]}"
    )
    reply_markup = {
        "inline_keyboard": [[
            {"text": "Acknowledge",    "callback_data": "acknowledge"},
            {"text": "Request Details","callback_data": "request_details"},
        ]]
    }
    _print_telegram_message("B", "Building Operator", bs["cycle"], text,
                            buttons=["Acknowledge", "Request Details"])
    log_event("telegram_message", "telegram",
              {"pipeline": "B", "recipient": "Building Operator",
               "cycle": bs["cycle"], "message_text": text})
    ok = _send_message(config.TELEGRAM_OPERATOR_CHAT_ID, text, reply_markup)
    log_event("telegram_sent", "telegram", {"pipeline": "B", "cycle": bs["cycle"], "ok": ok})
    return ok


def _print_telegram_message(pipeline, recipient, cycle, text, buttons=None):
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "")
    status = "SENT" if token else "NO TOKEN - would send"
    col    = _RED if pipeline == "B" else _YELLOW
    print(f"\n{col}[TELEGRAM] {'#'*48}{_RESET}")
    print(f"{_BOLD}[TELEGRAM] Pipeline {pipeline} -> {recipient}  "
          f"cycle={cycle}  [{status}]{_RESET}")
    print(f"{col}[TELEGRAM] {'#'*48}{_RESET}")
    for line in text.splitlines():
        clean = line.replace("*", "")
        print(f"[TELEGRAM]   {clean}")
    if buttons:
        print(f"[TELEGRAM]   [Buttons: {' | '.join(buttons)}]")
    print(f"{col}[TELEGRAM] {'#'*48}{_RESET}\n")


def _send_message(chat_id, text, reply_markup=None):
    """POST to Telegram Bot API. Returns False if token empty or request fails."""
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id:
        return False
    url     = _API_BASE.format(token=token, method="sendMessage")
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def handle_callback_query(update):
    """Handles Telegram inline button presses (stub for polling loop)."""
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    try:
        cq      = update["callback_query"]
        cq_id   = cq["id"]
        data    = cq.get("data", "")
        chat_id = cq["message"]["chat"]["id"]

        url = _API_BASE.format(token=token, method="answerCallbackQuery")
        requests.post(url, json={"callback_query_id": cq_id, "text": "Alert acknowledged."}, timeout=5)

        if data == "request_details":
            _send_message(str(chat_id), "Full anomaly details: check logs/events.jsonl for the latest CVC report.")
    except Exception:
        pass
