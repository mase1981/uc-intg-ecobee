"""ecobee switch entities (aux heat only, ventilator 20-minute timer)."""

import logging
from typing import Any, Awaitable, Callable

from ucapi import StatusCodes, switch
from ucapi_framework import SwitchEntity

from uc_intg_ecobee import thermostat as tstat
from uc_intg_ecobee.config import EcobeeConfig
from uc_intg_ecobee.const import HVAC_AUX_HEAT_ONLY
from uc_intg_ecobee.device import EcobeeAccount

_LOG = logging.getLogger(__name__)


class EcobeeSwitch(SwitchEntity):
    """Switch backed by a thermostat getter and a device setter."""

    def __init__(
        self,
        device_config: EcobeeConfig,
        device: EcobeeAccount,
        meta: dict,
        sub_id: str,
        label: str,
        getter: Callable[[dict], bool],
        setter: Callable[[EcobeeAccount, str, bool], Awaitable[None]],
    ) -> None:
        self._device = device
        self._tid = meta["id"]
        self._getter = getter
        self._setter = setter
        super().__init__(
            f"switch.{device_config.identifier}.{self._tid}_{sub_id}",
            f"{meta.get('name', 'ecobee')} {label}",
            [switch.Features.ON_OFF, switch.Features.TOGGLE],
            {switch.Attributes.STATE: switch.States.UNKNOWN},
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    def _value(self) -> bool:
        data = self._device.thermostat(self._tid)
        return bool(data and self._getter(data))

    async def sync_state(self) -> None:
        if not self._device.available(self._tid):
            self.update({switch.Attributes.STATE: switch.States.UNAVAILABLE})
            return
        self.update({switch.Attributes.STATE: switch.States.ON if self._value() else switch.States.OFF})

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict | None = None, *_a: Any) -> StatusCodes:
        try:
            if cmd_id == switch.Commands.ON:
                target = True
            elif cmd_id == switch.Commands.OFF:
                target = False
            elif cmd_id == switch.Commands.TOGGLE:
                target = not self._value()
            else:
                return StatusCodes.NOT_IMPLEMENTED
            await self._setter(self._device, self._tid, target)
            return StatusCodes.OK
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Switch command error (%s): %s", entity.id, cmd_id, err)
            return StatusCodes.SERVER_ERROR


def _ventilator_on(data: dict) -> bool:
    """Timer runs while ventilatorOffDateTime is in the future (thermostat local time)."""
    off_at = data.get("settings", {}).get("ventilatorOffDateTime") or ""
    now = data.get("thermostatTime") or ""
    return bool(off_at and now and off_at >= now)


def create_switches(device_config: EcobeeConfig, device: EcobeeAccount) -> list[SwitchEntity]:
    entities: list[SwitchEntity] = []
    for meta in device_config.thermostats:
        if meta.get("heat_pump"):
            entities.append(
                EcobeeSwitch(
                    device_config, device, meta, "aux_heat_only", "Aux Heat Only",
                    lambda t: tstat.hvac_mode(t) == HVAC_AUX_HEAT_ONLY,
                    lambda d, tid, on: d.set_aux_heat(tid, on),
                )
            )
        if meta.get("ventilator"):
            entities.append(
                EcobeeSwitch(
                    device_config, device, meta, "ventilator_timer", "Ventilator 20m Timer",
                    _ventilator_on,
                    lambda d, tid, on: d.set_ventilator_timer(tid, on),
                )
            )
    return entities
