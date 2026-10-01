"""ecobee thermostat climate entity."""

import logging
from typing import Any

from ucapi import StatusCodes, climate
from ucapi_framework import ClimateEntity

from uc_intg_ecobee import thermostat as tstat
from uc_intg_ecobee.config import EcobeeConfig
from uc_intg_ecobee.const import (
    FAN_LABELS,
    HVAC_AUTO,
    HVAC_AUX_HEAT_ONLY,
    HVAC_COOL,
    HVAC_HEAT,
    HVAC_OFF,
)
from uc_intg_ecobee.device import EcobeeAccount

_LOG = logging.getLogger(__name__)

_ECOBEE_TO_STATE = {
    HVAC_HEAT: climate.States.HEAT,
    HVAC_AUX_HEAT_ONLY: climate.States.HEAT,
    HVAC_COOL: climate.States.COOL,
    HVAC_AUTO: climate.States.HEAT_COOL,
    HVAC_OFF: climate.States.OFF,
}
_STATE_TO_ECOBEE = {
    "HEAT": HVAC_HEAT,
    "COOL": HVAC_COOL,
    "HEAT_COOL": HVAC_AUTO,
    "AUTO": HVAC_AUTO,
    "OFF": HVAC_OFF,
}


class EcobeeClimate(ClimateEntity):
    """One ecobee thermostat."""

    def __init__(self, device_config: EcobeeConfig, device: EcobeeAccount, meta: dict) -> None:
        self._device = device
        self._tid = meta["id"]
        self._celsius = bool(meta.get("celsius"))
        self._modes = []
        if meta.get("heat"):
            self._modes.append(HVAC_HEAT)
        if meta.get("cool"):
            self._modes.append(HVAC_COOL)
        if meta.get("heat") and meta.get("cool"):
            self._modes.append(HVAC_AUTO)

        features = [
            climate.Features.ON_OFF,
            climate.Features.CURRENT_TEMPERATURE,
            climate.Features.TARGET_TEMPERATURE,
            climate.Features.FAN,
        ]
        if meta.get("heat"):
            features.append(climate.Features.HEAT)
        if meta.get("cool"):
            features.append(climate.Features.COOL)
        if HVAC_AUTO in self._modes:
            features.append(climate.Features.TARGET_TEMPERATURE_RANGE)

        options = {
            climate.Options.TEMPERATURE_UNIT: "CELSIUS" if self._celsius else "FAHRENHEIT",
            climate.Options.TARGET_TEMPERATURE_STEP: 0.5,
            climate.Options.MIN_TEMPERATURE: tstat.to_display(meta.get("min_f", 45.0), self._celsius),
            climate.Options.MAX_TEMPERATURE: tstat.to_display(meta.get("max_f", 92.0), self._celsius),
            climate.Options.FAN_MODES: list(FAN_LABELS.values()),
        }
        super().__init__(
            f"climate.{device_config.identifier}.{self._tid}",
            meta.get("name", "ecobee"),
            features,
            {climate.Attributes.STATE: climate.States.UNKNOWN},
            options=options,
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        data = self._device.thermostat(self._tid)
        if data is None or not self._device.available(self._tid):
            self.update({climate.Attributes.STATE: climate.States.UNAVAILABLE})
            return
        mode = tstat.hvac_mode(data)
        runtime = data.get("runtime", {})
        attrs: dict[str, Any] = {
            climate.Attributes.STATE: _ECOBEE_TO_STATE.get(mode, climate.States.UNKNOWN),
            climate.Attributes.CURRENT_TEMPERATURE: tstat.to_display(
                tstat.f10_to_f(runtime.get("actualTemperature")), self._celsius
            ),
            climate.Attributes.FAN_MODE: FAN_LABELS.get(runtime.get("desiredFanMode", ""), "Auto"),
        }
        target = self._device.target(self._tid)
        if target is not None:
            attrs[climate.Attributes.TARGET_TEMPERATURE] = target
        if mode == HVAC_AUTO:
            heat_f, cool_f = tstat.setpoints_f(data)
            attrs[climate.Attributes.TARGET_TEMPERATURE_LOW] = tstat.to_display(heat_f, self._celsius)
            attrs[climate.Attributes.TARGET_TEMPERATURE_HIGH] = tstat.to_display(cool_f, self._celsius)
        self.update(attrs)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict | None = None, *_a: Any) -> StatusCodes:
        params = params or {}
        try:
            match cmd_id:
                case climate.Commands.ON:
                    await self._device.turn_on(self._tid)
                case climate.Commands.OFF:
                    await self._device.turn_off(self._tid)
                case climate.Commands.HVAC_MODE:
                    mode = _STATE_TO_ECOBEE.get(str(params.get("hvac_mode", "")).upper())
                    if mode is None or (mode != HVAC_OFF and mode not in self._modes):
                        return StatusCodes.BAD_REQUEST
                    await self._device.set_hvac_mode(self._tid, mode)
                case climate.Commands.TARGET_TEMPERATURE:
                    await self._device.set_target(self._tid, float(params["temperature"]))
                case climate.Commands.TARGET_TEMPERATURE_RANGE:
                    await self._device.set_range(
                        self._tid, float(params["temperature_low"]), float(params["temperature_high"])
                    )
                case climate.Commands.FAN_MODE:
                    label = str(params.get("fan_mode") or params.get("enum") or "")
                    fan = next((k for k, v in FAN_LABELS.items() if v.lower() == label.lower()), None)
                    if fan is None:
                        return StatusCodes.BAD_REQUEST
                    await self._device.set_fan_mode(self._tid, fan)
                case _:
                    return StatusCodes.NOT_IMPLEMENTED
            return StatusCodes.OK
        except (KeyError, ValueError) as err:
            _LOG.warning("[%s] Bad command %s %s: %s", entity.id, cmd_id, params, err)
            return StatusCodes.BAD_REQUEST
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Command error (%s): %s", entity.id, cmd_id, err)
            return StatusCodes.SERVER_ERROR


def create_climates(device_config: EcobeeConfig, device: EcobeeAccount) -> list[ClimateEntity]:
    return [EcobeeClimate(device_config, device, meta) for meta in device_config.thermostats]
