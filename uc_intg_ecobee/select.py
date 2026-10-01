"""ecobee select entities (preset/comfort setting, fan, fan min on time, humidifier)."""

import logging
from typing import Any, Awaitable, Callable

from ucapi import StatusCodes, select
from ucapi_framework import SelectEntity

from uc_intg_ecobee import thermostat as tstat
from uc_intg_ecobee.config import EcobeeConfig
from uc_intg_ecobee.const import FAN_LABELS, HUMIDIFIER_MODES, HUMIDITY_MAX, HUMIDITY_MIN
from uc_intg_ecobee.device import EcobeeAccount

_LOG = logging.getLogger(__name__)

OptionsFn = Callable[[EcobeeAccount, dict], dict[str, Any]]
CurrentFn = Callable[[EcobeeAccount, dict], Any]
SetFn = Callable[[EcobeeAccount, str, Any], Awaitable[None]]


class EcobeeSelect(SelectEntity):
    """Select backed by a label->value table computed from the thermostat."""

    def __init__(
        self,
        device_config: EcobeeConfig,
        device: EcobeeAccount,
        meta: dict,
        sub_id: str,
        label: str,
        options_fn: OptionsFn,
        current_fn: CurrentFn,
        set_fn: SetFn,
    ) -> None:
        self._device = device
        self._tid = meta["id"]
        self._options_fn = options_fn
        self._current_fn = current_fn
        self._set_fn = set_fn
        super().__init__(
            f"select.{device_config.identifier}.{self._tid}_{sub_id}",
            f"{meta.get('name', 'ecobee')} {label}",
            {
                select.Attributes.STATE: select.States.UNKNOWN,
                select.Attributes.OPTIONS: [],
                select.Attributes.CURRENT_OPTION: "",
            },
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    def _table(self) -> tuple[dict[str, Any], str]:
        data = self._device.thermostat(self._tid)
        if data is None:
            return {}, ""
        options = self._options_fn(self._device, data)
        value = self._current_fn(self._device, data)
        current = next((label for label, v in options.items() if v == value), "")
        return options, current

    async def sync_state(self) -> None:
        if not self._device.available(self._tid):
            self.update({select.Attributes.STATE: select.States.UNAVAILABLE})
            return
        options, current = self._table()
        self.update(
            {
                select.Attributes.STATE: select.States.ON,
                select.Attributes.OPTIONS: list(options.keys()),
                select.Attributes.CURRENT_OPTION: current,
            }
        )

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict | None = None, *_a: Any) -> StatusCodes:
        options, current = self._table()
        labels = list(options.keys())
        if not labels:
            return StatusCodes.SERVICE_UNAVAILABLE
        index = labels.index(current) if current in labels else 0
        cycle = bool((params or {}).get("cycle", False))
        match cmd_id:
            case select.Commands.SELECT_OPTION:
                option = (params or {}).get("option", "")
            case select.Commands.SELECT_FIRST:
                option = labels[0]
            case select.Commands.SELECT_LAST:
                option = labels[-1]
            case select.Commands.SELECT_NEXT:
                option = labels[(index + 1) % len(labels)] if cycle else labels[min(index + 1, len(labels) - 1)]
            case select.Commands.SELECT_PREVIOUS:
                option = labels[(index - 1) % len(labels)] if cycle else labels[max(index - 1, 0)]
            case _:
                return StatusCodes.NOT_IMPLEMENTED
        if option not in options:
            return StatusCodes.BAD_REQUEST
        try:
            await self._set_fn(self._device, self._tid, options[option])
            return StatusCodes.OK
        except ValueError as err:
            _LOG.warning("[%s] %s", entity.id, err)
            return StatusCodes.BAD_REQUEST
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Select command error (%s): %s", entity.id, cmd_id, err)
            return StatusCodes.SERVER_ERROR


def _preset_options(dev: EcobeeAccount, data: dict) -> dict[str, Any]:
    return {label: label for label in dev.preset_options(str(data.get("identifier")))}


def _humidity_options(_dev: EcobeeAccount, data: dict) -> dict[str, Any]:
    values = list(range(HUMIDITY_MIN, HUMIDITY_MAX + 1, 5))
    current = _humidity(_dev, data)
    if isinstance(current, int) and current not in values:
        values = sorted(values + [current])
    return {f"{v}%": v for v in values}


def _humidity(_dev: EcobeeAccount, data: dict) -> Any:
    try:
        return int(data.get("runtime", {}).get("desiredHumidity"))
    except (TypeError, ValueError):
        return None


def _fan_min_options(_dev: EcobeeAccount, data: dict) -> dict[str, Any]:
    values = list(range(0, 61, 5))
    current = data.get("settings", {}).get("fanMinOnTime")
    if isinstance(current, int) and current not in values:
        values = sorted(values + [current])
    return {f"{v} min/hour": v for v in values}


def create_selects(device_config: EcobeeConfig, device: EcobeeAccount) -> list[SelectEntity]:
    entities: list[SelectEntity] = []
    for meta in device_config.thermostats:
        entities.append(
            EcobeeSelect(
                device_config, device, meta, "preset", "Comfort Setting",
                _preset_options,
                lambda d, t: tstat.preset(t)[0],
                lambda d, tid, v: d.set_preset(tid, v),
            )
        )
        entities.append(
            EcobeeSelect(
                device_config, device, meta, "fan_mode", "Fan Mode",
                lambda d, t: {label: key for key, label in FAN_LABELS.items()},
                lambda d, t: t.get("runtime", {}).get("desiredFanMode"),
                lambda d, tid, v: d.set_fan_mode(tid, v),
            )
        )
        entities.append(
            EcobeeSelect(
                device_config, device, meta, "fan_min_on_time", "Fan Min On Time",
                _fan_min_options,
                lambda d, t: t.get("settings", {}).get("fanMinOnTime"),
                lambda d, tid, v: d.set_fan_min_on_time(tid, v),
            )
        )
        if meta.get("humidifier"):
            entities.append(
                EcobeeSelect(
                    device_config, device, meta, "humidifier_mode", "Humidifier Mode",
                    lambda d, t: {label: key for key, label in HUMIDIFIER_MODES.items()},
                    lambda d, t: t.get("settings", {}).get("humidifierMode"),
                    lambda d, tid, v: d.set_humidifier_mode(tid, v),
                )
            )
            entities.append(
                EcobeeSelect(
                    device_config, device, meta, "target_humidity", "Target Humidity",
                    _humidity_options, _humidity,
                    lambda d, tid, v: d.set_humidity(tid, v),
                )
            )
    return entities
