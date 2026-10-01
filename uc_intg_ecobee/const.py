"""Constants for the ecobee integration (values follow the Home Assistant ecobee integration)."""

# ecobee asks API clients not to poll more often than every 3 minutes.
POLL_INTERVAL = 180

# Device (account) states.
STATE_ON = "ON"
STATE_UNAVAILABLE = "UNAVAILABLE"
STATE_AUTH_REQUIRED = "AUTH_REQUIRED"

AUTH_CREDENTIALS = "credentials"
AUTH_API_KEY = "api_key"

ECOBEE_AUTH_URL = "https://www.ecobee.com/consumerportal/index.html"

# ecobee hvacMode values.
HVAC_HEAT = "heat"
HVAC_COOL = "cool"
HVAC_AUTO = "auto"
HVAC_OFF = "off"
HVAC_AUX_HEAT_ONLY = "auxHeatOnly"

# ecobee equipmentStatus entries -> activity label (None = not shown).
EQUIPMENT_ACTION: dict[str, str | None] = {
    "heatPump": "Heating",
    "heatPump2": "Heating",
    "heatPump3": "Heating",
    "compCool1": "Cooling",
    "compCool2": "Cooling",
    "auxHeat1": "Heating",
    "auxHeat2": "Heating",
    "auxHeat3": "Heating",
    "fan": "Fan",
    "humidifier": None,
    "dehumidifier": "Drying",
    "ventilator": "Fan",
    "economizer": "Fan",
    "compHotWater": None,
    "auxHotWater": None,
    "compWaterHeater": None,
}
ACTION_PRIORITY = ["Heating", "Cooling", "Drying", "Fan"]

FAN_AUTO = "auto"
FAN_ON = "on"
FAN_LABELS: dict[str, str] = {FAN_AUTO: "Auto", FAN_ON: "On"}

HUMIDIFIER_MODES: dict[str, str] = {"off": "Off", "auto": "Auto", "manual": "Manual"}
HUMIDITY_MIN = 15
HUMIDITY_MAX = 50

# Preset labels that are not ecobee comfort settings.
PRESET_AWAY_INDEFINITELY = "Away Indefinitely"
PRESET_RESUME = "Resume Schedule"
PRESET_TEMPERATURE = "Temperature Hold"
PRESET_VACATION = "Vacation"

# holdAction setting -> (holdType, holdHours).
HOLD_ACTION: dict[str, tuple[str, int | None]] = {
    "useEndTime2hour": ("holdHours", 2),
    "useEndTime4hour": ("holdHours", 4),
    "indefinite": ("indefinite", None),
}
DEFAULT_HOLD = ("nextTransition", None)

# Default setpoint limits (°F) when the thermostat does not report ranges.
DEFAULT_MIN_F = 45.0
DEFAULT_MAX_F = 92.0

# ecobee "unknown" sentinels.
ECOBEE_STATE_UNKNOWN = -5002
ECOBEE_STATE_CALIBRATING = -5003

ECOBEE_MODEL_TO_NAME: dict[str, str] = {
    "idtSmart": "ecobee Smart",
    "idtEms": "ecobee Smart EMS",
    "siSmart": "ecobee Si Smart",
    "siEms": "ecobee Si EMS",
    "athenaSmart": "ecobee3 Smart",
    "athenaEms": "ecobee3 EMS",
    "corSmart": "Carrier/Bryant Cor",
    "nikeSmart": "ecobee3 lite Smart",
    "nikeEms": "ecobee3 lite EMS",
    "apolloSmart": "ecobee4 Smart",
    "vulcanSmart": "ecobee4 Smart",
    "aresSmart": "ecobee Smart Premium",
    "artemisSmart": "ecobee Smart Enhanced",
    "attisRetail": "ecobee Smart Thermostat with Voice Control",
    "attisPro": "ecobee Smart Thermostat Lite",
}

# ecobee weatherSymbol -> label.
WEATHER_SYMBOLS: dict[int, str] = {
    0: "Sunny",
    1: "Partly Cloudy",
    2: "Partly Cloudy",
    3: "Cloudy",
    4: "Cloudy",
    5: "Cloudy",
    6: "Rainy",
    7: "Snowy, Rainy",
    8: "Pouring",
    9: "Hail",
    10: "Snowy",
    11: "Snowy",
    12: "Snowy, Rainy",
    13: "Heavy Snow",
    14: "Hail",
    15: "Thunderstorm",
    16: "Windy",
    17: "Tornado",
    18: "Fog",
    19: "Hazy",
    20: "Hazy",
    21: "Hazy",
}
