"""ecobee sensor entities (thermostat readings, weather, remote sensors, air quality)."""

import logging
from typing import Any, Callable

from ucapi import sensor
from ucapi_framework import SensorEntity

from uc_intg_ecobee import thermostat as tstat
from uc_intg_ecobee.config import EcobeeConfig
from uc_intg_ecobee.const import (
    ECOBEE_MODEL_TO_NAME,
    ECOBEE_STATE_CALIBRATING,
    ECOBEE_STATE_UNKNOWN,
    WEATHER_SYMBOLS,
)
from uc_intg_ecobee.device import EcobeeAccount

_LOG = logging.getLogger(__name__)

_UNKNOWN = (ECOBEE_STATE_UNKNOWN, ECOBEE_STATE_CALIBRATING, str(ECOBEE_STATE_UNKNOWN),
            str(ECOBEE_STATE_CALIBRATING), "unknown", None, "")

ValueFn = Callable[[dict], Any]


def _f10_to_c(value: Any) -> float | None:
    """ecobee tenths of °F -> °C (sensor entities report °C; the Remote converts)."""
    if value in _UNKNOWN:
        return None
    f = tstat.f10_to_f(value)
    return None if f is None else round(tstat.f_to_c(f), 1)


def _number(value: Any) -> Any:
    if value in _UNKNOWN:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class EcobeeSensor(SensorEntity):
    """Sensor whose value is derived from the thermostat JSON."""

    def __init__(
        self,
        device_config: EcobeeConfig,
        device: EcobeeAccount,
        meta: dict,
        sub_id: str,
        name: str,
        value_fn: ValueFn,
        device_class: sensor.DeviceClasses = sensor.DeviceClasses.CUSTOM,
        unit: str | None = None,
        decimals: int = 0,
    ) -> None:
        self._device = device
        self._tid = meta["id"]
        self._value_fn = value_fn
        self._binary = device_class == sensor.DeviceClasses.BINARY
        options: dict[str, Any] = {}
        if device_class == sensor.DeviceClasses.CUSTOM:
            options[sensor.Options.CUSTOM_UNIT] = unit or ""
        if decimals:
            options[sensor.Options.DECIMALS] = decimals
        attributes: dict[str, Any] = {sensor.Attributes.STATE: sensor.States.UNKNOWN, sensor.Attributes.VALUE: ""}
        if self._binary and unit:
            attributes[sensor.Attributes.UNIT] = unit
        super().__init__(
            f"sensor.{device_config.identifier}.{self._tid}_{sub_id}",
            name,
            [],
            attributes,
            device_class=device_class,
            options=options,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        data = self._device.thermostat(self._tid)
        if data is None or not self._device.available(self._tid):
            self.update({sensor.Attributes.STATE: sensor.States.UNAVAILABLE})
            return
        try:
            value = self._value_fn(data)
        except (KeyError, IndexError, TypeError, ValueError):
            value = None
        if value is None:
            self.update({sensor.Attributes.STATE: sensor.States.UNKNOWN})
            return
        if self._binary:
            value = "on" if value else "off"
        self.update({sensor.Attributes.STATE: sensor.States.ON, sensor.Attributes.VALUE: value})


def _remote_capability(sensor_id: str, cap_type: str) -> ValueFn:
    def _get(data: dict) -> Any:
        for rs in data.get("remoteSensors", []):
            if str(rs.get("id")) != sensor_id:
                continue
            for cap in rs.get("capability", []):
                if cap.get("type") == cap_type:
                    return cap.get("value")
        return None

    return _get


def _forecast(field: str) -> ValueFn:
    return lambda d: (d.get("weather", {}).get("forecasts") or [{}])[0].get(field)


def _sensor_slug(sensor_id: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in sensor_id)


def create_sensors(device_config: EcobeeConfig, device: EcobeeAccount) -> list[SensorEntity]:
    entities: list[SensorEntity] = []
    for meta in device_config.thermostats:
        base = meta.get("name", "ecobee")

        def add(sub_id: str, label: str, fn: ValueFn, **kw: Any) -> None:
            entities.append(EcobeeSensor(device_config, device, meta, sub_id, f"{base} {label}", fn, **kw))

        add("temperature", "Temperature",
            lambda d: _f10_to_c(d.get("runtime", {}).get("actualTemperature")),
            device_class=sensor.DeviceClasses.TEMPERATURE, decimals=1)
        add("humidity", "Humidity",
            lambda d: _number(d.get("runtime", {}).get("actualHumidity")),
            device_class=sensor.DeviceClasses.HUMIDITY)
        add("activity", "Activity", tstat.equipment_action)
        add("hvac_mode", "HVAC Mode", lambda d: tstat.hvac_mode(d).replace("auxHeatOnly", "aux heat").title())
        add("comfort", "Comfort Setting", lambda d: tstat.preset(d)[0])
        add("outdoor_temperature", "Outdoor Temperature",
            lambda d: _f10_to_c(_forecast("temperature")(d)),
            device_class=sensor.DeviceClasses.TEMPERATURE, decimals=1)
        add("outdoor_humidity", "Outdoor Humidity",
            lambda d: _number(_forecast("relativeHumidity")(d)),
            device_class=sensor.DeviceClasses.HUMIDITY)
        add("weather", "Weather", lambda d: WEATHER_SYMBOLS.get(_number(_forecast("weatherSymbol")(d))))
        add("model", "Model", lambda d: ECOBEE_MODEL_TO_NAME.get(d.get("modelNumber", ""), d.get("modelNumber")))

        for rs in meta.get("sensors", []):
            sid, name, caps = rs.get("id", ""), rs.get("name", ""), rs.get("capabilities", [])
            slug = _sensor_slug(sid)
            is_thermostat = rs.get("type") == "thermostat"
            if "occupancy" in caps:
                label = "Occupancy" if is_thermostat else f"{name} Occupancy"
                add(f"{slug}_occupancy", label,
                    lambda d, f=_remote_capability(sid, "occupancy"): None if f(d) is None else f(d) == "true",
                    device_class=sensor.DeviceClasses.BINARY, unit="occupancy")
            if is_thermostat:
                continue  # thermostat's own temperature/humidity are covered above
            if "temperature" in caps:
                add(f"{slug}_temperature", f"{name} Temperature",
                    lambda d, f=_remote_capability(sid, "temperature"): _f10_to_c(f(d)),
                    device_class=sensor.DeviceClasses.TEMPERATURE, decimals=1)
            if "humidity" in caps:
                add(f"{slug}_humidity", f"{name} Humidity",
                    lambda d, f=_remote_capability(sid, "humidity"): _number(f(d)),
                    device_class=sensor.DeviceClasses.HUMIDITY)

        # Air quality (ecobee Smart Premium) - values come from runtime like HA.
        caps = {c for rs in meta.get("sensors", []) for c in rs.get("capabilities", [])}
        if "co2PPM" in caps:
            add("co2", "CO2", lambda d: _number(d.get("runtime", {}).get("actualCO2")), unit="ppm")
        if "vocPPM" in caps:
            add("voc", "VOC", lambda d: _number(d.get("runtime", {}).get("actualVOC")), unit="µg/m³")
        if "airQuality" in caps:
            add("air_quality", "Air Quality Score", lambda d: _number(d.get("runtime", {}).get("actualAQScore")))
    return entities
