"""Pure helpers that interpret an ecobee thermostat JSON object.

Logic follows the Home Assistant ecobee climate entity. ecobee reports
temperatures in tenths of °F; values are converted to the thermostat's display
unit (settings.useCelsius).
"""

from datetime import date, timedelta
from typing import Any

from uc_intg_ecobee.const import (
    ACTION_PRIORITY,
    DEFAULT_HOLD,
    DEFAULT_MAX_F,
    DEFAULT_MIN_F,
    EQUIPMENT_ACTION,
    HOLD_ACTION,
    HVAC_AUX_HEAT_ONLY,
    HVAC_HEAT,
    HVAC_OFF,
    PRESET_AWAY_INDEFINITELY,
    PRESET_TEMPERATURE,
    PRESET_VACATION,
)


# -- units -------------------------------------------------------------
def f10_to_f(value: Any) -> float | None:
    try:
        return float(value) / 10.0
    except (TypeError, ValueError):
        return None


def f_to_c(value: float) -> float:
    return (value - 32.0) * 5.0 / 9.0


def c_to_f(value: float) -> float:
    return value * 9.0 / 5.0 + 32.0


def to_display(value_f: float | None, celsius: bool) -> float | None:
    """°F -> display unit, rounded to 0.1."""
    if value_f is None:
        return None
    return round(f_to_c(value_f) if celsius else value_f, 1)


def from_display(value: float, celsius: bool) -> float:
    """Display unit -> °F."""
    return c_to_f(float(value)) if celsius else float(value)


# -- metadata ----------------------------------------------------------
def _sensor_capabilities(thermostat: dict) -> list[dict[str, Any]]:
    sensors = []
    for sensor in thermostat.get("remoteSensors", []) or []:
        caps = [c.get("type") for c in sensor.get("capability", []) if c.get("type")]
        sensors.append(
            {
                "id": str(sensor.get("id", "")),
                "name": sensor.get("name", ""),
                "type": sensor.get("type", ""),
                "capabilities": caps,
            }
        )
    return sensors


def build_meta(thermostat: dict) -> dict[str, Any]:
    """Static description of a thermostat, stored in the config."""
    settings = thermostat.get("settings", {})
    heat = bool(settings.get("heatStages")) or bool(settings.get("hasHeatPump"))
    cool = bool(settings.get("coolStages"))
    low = f10_to_f(settings.get("heatRangeLow"))
    high = f10_to_f(settings.get("coolRangeHigh"))
    if not cool:
        high = f10_to_f(settings.get("heatRangeHigh")) or high
    if not heat:
        low = f10_to_f(settings.get("coolRangeLow")) or low
    return {
        "id": str(thermostat.get("identifier", "")),
        "name": thermostat.get("name", "ecobee"),
        "model": thermostat.get("modelNumber", ""),
        "heat": heat,
        "cool": cool,
        "heat_pump": bool(settings.get("hasHeatPump")),
        "humidifier": bool(settings.get("hasHumidifier")),
        "ventilator": str(settings.get("ventilatorType", "none")) not in ("none", ""),
        "celsius": bool(settings.get("useCelsius")),
        "min_f": low if low else DEFAULT_MIN_F,
        "max_f": high if high else DEFAULT_MAX_F,
        "sensors": _sensor_capabilities(thermostat),
    }


# -- state helpers -----------------------------------------------------
def hvac_mode(thermostat: dict) -> str:
    return thermostat.get("settings", {}).get("hvacMode", HVAC_OFF)


def is_heat_mode(mode: str) -> bool:
    return mode in (HVAC_HEAT, HVAC_AUX_HEAT_ONLY)


def comfort_settings(thermostat: dict) -> dict[str, str]:
    """climateRef -> name."""
    return {
        c["climateRef"]: c["name"]
        for c in thermostat.get("program", {}).get("climates", [])
        if "climateRef" in c and "name" in c
    }


def is_indefinite_hold(start: str, end: str) -> bool:
    """ecobee does not flag indefinite holds; HA treats holds over 1 year as indefinite."""
    try:
        return date.fromisoformat(end) - date.fromisoformat(start) > timedelta(days=365)
    except (TypeError, ValueError):
        return False


def preset(thermostat: dict) -> tuple[str | None, str | None]:
    """Return (preset label, running vacation name)."""
    comforts = comfort_settings(thermostat)
    for event in thermostat.get("events", []):
        if not event.get("running"):
            continue
        etype = event.get("type", "")
        if etype == "hold":
            ref = event.get("holdClimateRef", "")
            if ref == "away" and is_indefinite_hold(event.get("startDate", ""), event.get("endDate", "")):
                return PRESET_AWAY_INDEFINITELY, None
            if ref in comforts:
                return comforts[ref], None
            return PRESET_TEMPERATURE, None
        if etype.startswith("auto"):
            return etype[4:].title(), None
        if etype == "vacation":
            return PRESET_VACATION, event.get("name")
    current = thermostat.get("program", {}).get("currentClimateRef")
    return comforts.get(current), None


def equipment_action(thermostat: dict) -> str:
    status = thermostat.get("equipmentStatus", "") or ""
    actions = {EQUIPMENT_ACTION.get(s) for s in status.split(",") if s}
    for action in ACTION_PRIORITY:
        if action in actions:
            return action
    return "Idle"


def hold_params(thermostat: dict) -> tuple[str, int | None]:
    """(holdType, holdHours) from the thermostat's 'hold action' preference."""
    return HOLD_ACTION.get(thermostat.get("settings", {}).get("holdAction", ""), DEFAULT_HOLD)


def setpoints_f(thermostat: dict) -> tuple[float, float]:
    runtime = thermostat.get("runtime", {})
    return f10_to_f(runtime.get("desiredHeat")) or 0.0, f10_to_f(runtime.get("desiredCool")) or 0.0


def min_delta_f(thermostat: dict) -> float:
    return f10_to_f(thermostat.get("settings", {}).get("heatCoolMinDelta")) or 0.0
