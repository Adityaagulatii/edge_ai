"""
historical_data.py
Synthetic OHLC temperature-delta data for the candlestick charts.
Delta = hub_avg_temp - setpoint (Δ°F). Positive = hub runs hot, negative = cold.

Each candle = one period's aggregated delta across all online VAVs in the hub.
Timeframes: "10d" (10 daily), "1m" (30 daily), "3m" (13 weekly), "1y" (12 monthly)

Splunk path (is_iaif=False): slow correction, wide wicks (long drift periods).
AI path    (is_iaif=True):   fast correction, tight wicks (rapid reversion to 0).
"""
import random
import datetime
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

# Characteristic delta per hub derived from BMS baseline data
# Hub-1: mostly undercooled rooms (VAV-1,-3,-4 cold)
# Hub-2: VAV-6 overheated, VAV-7 offline
# Hub-3: VAV-11 cold, mostly neutral
# Hub-4: VAV-20 overheated, VAV-18 offline
# Hub-5: VAV-22 very hot (+8), VAV-21,-23 cold/offline
_HUB_BIAS = {
    "Hub-1": -2.0,   # tends to run cold
    "Hub-2": +1.5,   # slight overheating bias
    "Hub-3": -1.0,   # mild undercooling
    "Hub-4": +1.8,   # moderate overheating
    "Hub-5": +2.5,   # largest deviation (VAV-22 drags it hot)
}

# Seasonal weather modifier: Boston temps push HVAC load up in summer, down in winter
# Candles further in the past use an estimated seasonal offset
_SEASONAL = [
    -1.5, -1.2, -0.8, 0.0, +0.5, +1.2,  # Jan–Jun
    +1.8, +1.6, +1.0, +0.4, -0.3, -1.0, # Jul–Dec
]


def _seasonal_factor(date_offset_days):
    """Returns a weather-load modifier for a day offset_days in the past."""
    today = datetime.date.today()
    d = today - datetime.timedelta(days=date_offset_days)
    return _SEASONAL[d.month - 1]


def _make_periods(timeframe):
    """
    Returns list of (label, days_ago_start) for candle generation.
    days_ago_start = midpoint of that candle's period, used for seasonal factor.
    """
    today = datetime.date.today()
    if timeframe == "1d":
        # 24 hourly candles (00:00–23:00) full day; pipeline tick strip drawn separately in JS
        return [(f"{h:02d}:00", 0) for h in range(24)]

    if timeframe == "10d":
        return [(
            (today - datetime.timedelta(days=9-i)).strftime("%b %d"),
            9 - i
        ) for i in range(10)]

    if timeframe == "1m":
        return [(
            (today - datetime.timedelta(days=29-i)).strftime("%b %d"),
            29 - i
        ) for i in range(30)]

    if timeframe == "3m":
        # 63 daily candles — same density as 1m, labels show month name at each month boundary
        labels = []
        for i in range(62, -1, -1):
            d = today - datetime.timedelta(days=i)
            # show "Jan", "Feb" at the 1st of each month, blank otherwise
            label = d.strftime("%b") if d.day == 1 else ""
            labels.append((label, i))
        return labels

    # "1y" — 52 weekly candles, label at each month boundary
    labels = []
    for i in range(51, -1, -1):
        d = today - datetime.timedelta(weeks=i)
        # show month name when this week contains the 1st of a month
        week_start = d - datetime.timedelta(days=d.weekday())
        label = week_start.strftime("%b") if week_start.day <= 7 else ""
        labels.append((label, i * 7))
    return labels


def generate_ohlc(hub_id, timeframe, is_iaif=False):
    """
    Returns list[dict]: {idx, open, high, low, close, label}
    All values are Δ°F from setpoint (0 = exactly at setpoint).

    Generates a genuine random walk so the chart looks like a real market chart:
      - open of each candle = close of previous candle (continuous chain)
      - price wanders up/down with realistic volatility per timeframe
      - wicks always extend beyond the body
    """
    rng = random.Random(hub_id + timeframe + ("ai" if is_iaif else "sp"))
    bias = _HUB_BIAS.get(hub_id, 0.0)
    periods = _make_periods(timeframe)

    # Per-timeframe body volatility and wick size
    body_vol = {"1d": 0.30, "10d": 1.0, "1m": 0.85, "3m": 1.3, "1y": 1.6}[timeframe]
    wick_vol = {"1d": 0.15, "10d": 0.5, "1m": 0.45, "3m": 0.7, "1y": 0.9}[timeframe]

    candles = []
    price = bias  # start near hub's typical operating delta

    for idx, (label, days_ago) in enumerate(periods):
        seasonal = _seasonal_factor(days_ago)
        # Tiny drift toward hub bias (very mild — keeps series grounded, not trapped)
        drift_pull = (bias + seasonal * 0.4 - price) * 0.06

        open_d = price
        move   = rng.gauss(drift_pull, body_vol)
        close_d = open_d + move

        # Wicks always protrude beyond the body
        wick_up = abs(rng.gauss(0, wick_vol)) + 0.15
        wick_dn = abs(rng.gauss(0, wick_vol)) + 0.15
        high_d  = max(open_d, close_d) + wick_up
        low_d   = min(open_d, close_d) - wick_dn

        candles.append({
            "idx":   idx,
            "open":  round(open_d,  2),
            "high":  round(high_d,  2),
            "low":   round(low_d,   2),
            "close": round(close_d, 2),
            "label": label,
        })
        price = close_d  # next open = this close

    return candles


def generate_line_1d(hub_id, is_iaif=False):
    """
    Returns list[dict]: {idx, time_label, temp, is_hour}
    96 points = 24 hours × 4 per hour (every 15 min).
    temp is absolute °F (delta + 74).
    is_iaif=True  → tight mean-reversion, stays close to setpoint.
    is_iaif=False → slow drift, wider excursions.
    """
    rng = random.Random(hub_id + "1d_line" + ("ai" if is_iaif else "sp"))
    bias = _HUB_BIAS.get(hub_id, 0.0)
    setpoint = 74.0
    price = setpoint + bias   # start at hub's typical temp

    points = []
    for i in range(96):
        hh, mm = divmod(i * 15, 60)
        label = f"{hh:02d}:00" if mm == 0 else ""
        is_hour = mm == 0

        # Move
        if is_iaif:
            # AI: strong pull toward setpoint each step
            correction = (setpoint - price) * 0.35
            price = price + correction + rng.gauss(0, 0.12)
        else:
            # Splunk: weak drift, slow reversion
            drift = (setpoint + bias - price) * 0.04
            price = price + drift + rng.gauss(0, 0.28)

        points.append({
            "idx":        i,
            "time_label": label,
            "temp":       round(price, 2),
            "is_hour":    is_hour,
        })

    return points


def classify_rooms(hub_id):
    """
    Classify VAVs in a hub into 4 quadric categories based on baseline delta.
    Returns {'always_over': [...], 'optimal': [...], 'no_data': [...], 'always_low': [...]}
    """
    _BASELINE_DELTA = {
        "VAV-1":  -4.0, "VAV-2":  -2.0, "VAV-3":  -6.0, "VAV-4":  -3.0, "VAV-5":   0.0,
        "VAV-6":  +4.0, "VAV-7":   None, "VAV-8":  +1.0, "VAV-9":  -1.0, "VAV-10": -2.0,
        "VAV-11": -6.0, "VAV-12": -1.0, "VAV-13": -1.0, "VAV-14": +1.0, "VAV-15":  0.0,
        "VAV-16": +2.0, "VAV-17": +2.0, "VAV-18":  None, "VAV-19": -1.0, "VAV-20": +5.0,
        "VAV-21": -4.0, "VAV-22": +8.0, "VAV-23":  None, "VAV-24":  0.0, "VAV-25":  0.0,
        "VAV-26": -2.0,
    }
    _ZONE_MAP = {
        "Hub-1": ["VAV-1","VAV-2","VAV-3","VAV-4","VAV-5"],
        "Hub-2": ["VAV-6","VAV-7","VAV-8","VAV-9","VAV-10"],
        "Hub-3": ["VAV-11","VAV-12","VAV-13","VAV-14","VAV-15"],
        "Hub-4": ["VAV-16","VAV-17","VAV-18","VAV-19","VAV-20"],
        "Hub-5": ["VAV-21","VAV-22","VAV-23","VAV-24","VAV-25","VAV-26"],
    }
    eps = config.EPSILON_DIV
    result = {"always_over": [], "optimal": [], "no_data": [], "always_low": []}
    for vav in _ZONE_MAP.get(hub_id, []):
        d = _BASELINE_DELTA.get(vav)
        if d is None:
            result["no_data"].append(vav)
        elif d > eps:
            result["always_over"].append(vav)
        elif d < -eps:
            result["always_low"].append(vav)
        else:
            result["optimal"].append(vav)
    return result
