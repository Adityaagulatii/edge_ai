OLLAMA_URL   = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"

# Two-level model config
HUB_MODEL      = "llama3.2"
CVC_MODEL      = "llama3.2"
HUB_OLLAMA_URL = "http://localhost:11434"
CVC_OLLAMA_URL = "http://localhost:11434"

# Zone → Hub mapping (5 edge hubs, sequential split)
ZONE_MAP = {
    "Hub-1": {"vavs": ["VAV-1","VAV-2","VAV-3","VAV-4","VAV-5"],              "rtus": ["RTU-6"]},
    "Hub-2": {"vavs": ["VAV-6","VAV-7","VAV-8","VAV-9","VAV-10"],             "rtus": ["RTU-9"]},
    "Hub-3": {"vavs": ["VAV-11","VAV-12","VAV-13","VAV-14","VAV-15"],          "rtus": ["RTU-10"]},
    "Hub-4": {"vavs": ["VAV-16","VAV-17","VAV-18","VAV-19","VAV-20"],          "rtus": ["RTU-11"]},
    "Hub-5": {"vavs": ["VAV-21","VAV-22","VAV-23","VAV-24","VAV-25","VAV-26"], "rtus": []},
}

HUB_REPORT_TIMEOUT   = 12    # seconds CVC waits for all hub reports per cycle
SEVERITY_CVC_HANDLES = {"critical"}

TELEGRAM_BOT_TOKEN        = ""
TELEGRAM_ENGINEER_CHAT_ID = ""
TELEGRAM_OPERATOR_CHAT_ID = ""

POLL_INTERVAL = 5           # seconds  (5 for demo, 900 for production)
WEATHER_LAT   = 42.3601     # Boston — change to actual building location
WEATHER_LON   = -71.0589

# IAIF thresholds
EPSILON_DIV          = 2.0   # degF deviation from setpoint to count as anomalous
DIV_THRESHOLD_MOD    = 0.15  # divergence_score for moderate trigger
DIV_THRESHOLD_CRIT   = 0.40  # divergence_score for critical trigger
EFE_THRESHOLD        = 0.15  # fraction over expected power
NO_DATA_ESCALATE_CYCLES = 2  # cycles before persistent No Data escalates to engineer

# Mock data baselines
BASE_WATTS       = 5000
WATTS_PER_DEVICE = 50
RTU_OVERCOOL_THRESH = 45     # degF discharge temp
