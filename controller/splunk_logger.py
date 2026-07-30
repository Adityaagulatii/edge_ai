import json
import os
import threading
from datetime import datetime, timezone

_LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "events.jsonl")
_lock = threading.Lock()


def log_event(event_type, source, payload):
    """
    Appends a JSON line to logs/events.jsonl.
    event_type: "hub_sensor_data" | "hub_prompt" | "hub_llm_response" |
                "hub_report" | "hub_action" | "ollama_failure" |
                "cvc_prompt" | "cvc_llm_response" | "cvc_action" |
                "telegram_message" | "telegram_sent"
    source:     hub_id or "cvc" or "telegram"
    payload:    any JSON-serializable dict
    """
    entry = {
        "ts":         datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "source":     source,
        "payload":    payload,
    }
    line = json.dumps(entry, default=str)
    os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
    with _lock:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
