# IAIF — Intelligent Autonomous Infrastructure Framework
### Pipeline Design & Implementation

---

## Pipeline Design

| Version | File | Key Change |
|---|---|---|
| **V1** | `Pipeline_suggestion_1.pdf` | Initial full architecture — Edge Hub → LLM → CBC Orchestrator → Telegram |
| **V2** | `Pipeline_suggestion_2.pdf` | Added **Signal Lookout** gate — LLM only fires when anomaly detected |

---

## Pipeline V2 Architecture

```
External Inputs
  Open-Meteo Weather API
  Cisco WiFi Device Count
  Smart Power Meter per Zone
  Cisco Catalyst Center PoE
          │
          ▼
┌─────────────────────────────────────────────┐
│     Splunk Edge Hub  (iMX8M+ 8GB NPU)       │
│                                             │
│  Onboard Sensors ──► Signal Lookout ◄───────┤
│  temp · humidity       (IAIF gate)          │
│  light · sound              │               │
│                         YES │ anomaly?      │
│                             ▼               │
│  Prompt Assembly ◄─── AI Orchestrator       │
│       │                     │               │
│       ▼                     │               │
│  Ollama LLM (local)         │               │
│  ARM NEON + NPU             │               │
│       │ recommendation      │               │
│       └──────────────────── ┘               │
│                             │               │
│              MQTT Broker ◄──┘               │
│              Splunk Forwarder               │
└─────────────────────────────────────────────┘
                    │
                    ▼
        CBC Controller (OpenShift)
         ┌──────────────────┐
         │  Splunk Enterprise│
         │  Telegram Bot     │──► Building Operator (Acknowledge / Override)
         │  IoT Engineer     │──► Direct SPL Query (15-min poll)
         └──────────────────┘
```

---

## What V2 Adds Over V1

**Signal Lookout** is the core IAIF innovation — it makes the pipeline *intermittent*:

```
V1:  sensors → LLM every 15 min regardless        (wasteful on 2.3 TOPS NPU)

V2:  sensors → Signal Lookout → anomaly? → LLM    (only when needed)
                              → nothing? → ask IoT Engineer
```

Three triggers in Signal Lookout:

| Trigger | What it detects | Severity |
|---|---|---|
| **Sensor Loss** | VAV goes offline mid-cycle | Critical |
| **Belief Divergence** | Zone temps vs setpoints ratio > threshold | Moderate / Critical |
| **EFE Error** | Actual PoE watts vs expected (occupancy proxy) | Moderate |

---

## Code Structure

```
edge/
  signal_lookout.py    ← Signal Lookout — 3 IAIF triggers (the V2 innovation)
  prompt_assembly.py   ← builds LLM prompt from sensor context
  edge_hub.py          ← per-hub daemon: collects sensors, runs IAIF loop
  ollama_client.py     ← local Ollama inference (no cloud)

cvc/
  cvc_orchestrator.py  ← CBC AI Orchestrator — cross-hub aggregation
  aggregator.py        ← merges hub reports into building state
  cvc_prompt.py        ← building-level LLM prompt

controller/
  telegram_bot.py      ← Pipeline A (engineer summary) + Pipeline B (critical alert)
  splunk_logger.py     ← structured event logging

data_sources/
  bms_floor_plan.py    ← VAV/RTU sensor data (26 zones, 5 hubs)
  weather_api.py       ← Open-Meteo integration + mock fallback
  scenarios.py         ← demo scenarios (baseline, heatwave, cold snap, fault)

iaif_mini_demo.py      ← runnable demo of the full pipeline
config.py              ← thresholds, hub map, Ollama endpoints
```

---

## Run the Demo

```bash
# No setup needed — uses mock LLM responses
python -X utf8 iaif_mini_demo.py

# With real Ollama (pull llama3.2 first)
python -X utf8 iaif_mini_demo.py --live
```

Shows 3 scenarios walking through the exact Pipeline V2 flow:
1. Solar gain overheating (Signal Lookout → LLM → auto-correct setpoint)
2. Server room cold bleed (context-aware response vs dumb threshold)
3. Critical multi-hub event (CVC escalation + Telegram alert)

---

## Why This Beats Standard Splunk Edge Hub

| | Splunk Edge (standard) | IAIF Pipeline V2 |
|---|---|---|
| Anomaly detection | Threshold rules | Signal Lookout (3 triggers) |
| LLM usage | — | Only when anomaly detected |
| Auto setpoint correction | ❌ waits for human | ✅ < 15 seconds |
| Cross-hub awareness | ❌ | ✅ CBC Orchestrator |
| Human asked if borderline | ❌ | ✅ IoT Engineer prompt |
| Works fully offline | ⚠️ | ✅ local Ollama |
| Time to correction | 15–45 min | < 15 sec |
