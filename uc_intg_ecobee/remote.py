"""ecobee remote entity - thermostat control as simple commands for activities."""

import logging
from typing import Any

from ucapi import StatusCodes, remote
from ucapi.ui import Buttons, Size, UiPage, create_btn_mapping, create_ui_text
from ucapi_framework import RemoteEntity

from uc_intg_ecobee.config import EcobeeConfig
from uc_intg_ecobee.const import (
    FAN_AUTO,
    FAN_ON,
    HVAC_AUTO,
    HVAC_COOL,
    HVAC_HEAT,
    HVAC_OFF,
    PRESET_AWAY_INDEFINITELY,
    PRESET_RESUME,
)
from uc_intg_ecobee.device import EcobeeAccount

_LOG = logging.getLogger(__name__)

# Built-in ecobee comfort settings.
COMFORT_COMMANDS = {"PRESET_HOME": "Home", "PRESET_AWAY": "Away", "PRESET_SLEEP": "Sleep"}


class EcobeeRemote(RemoteEntity):
    """Simple commands + button mapping for one thermostat."""

    def __init__(self, device_config: EcobeeConfig, device: EcobeeAccount, meta: dict) -> None:
        self._device = device
        self._tid = meta["id"]
        modes = []
        if meta.get("heat"):
            modes.append("MODE_HEAT")
        if meta.get("cool"):
            modes.append("MODE_COOL")
        if meta.get("heat") and meta.get("cool"):
            modes.append("MODE_AUTO")
        modes.append("MODE_OFF")
        simple_commands = (
            ["POWER_TOGGLE", "POWER_ON", "POWER_OFF", "TEMP_UP", "TEMP_DOWN"]
            + modes
            + list(COMFORT_COMMANDS.keys())
            + ["PRESET_AWAY_INDEFINITELY", "RESUME_SCHEDULE", "FAN_AUTO", "FAN_ON"]
        )
        mode_items = [
            create_ui_text(cmd.replace("MODE_", "").title(), i, 0, cmd=cmd) for i, cmd in enumerate(modes)
        ]
        super().__init__(
            f"remote.{device_config.identifier}.{self._tid}",
            f"{meta.get('name', 'ecobee')} Remote",
            [remote.Features.ON_OFF, remote.Features.TOGGLE, remote.Features.SEND_CMD],
            {remote.Attributes.STATE: remote.States.UNKNOWN},
            simple_commands=simple_commands,
            button_mapping=[
                create_btn_mapping(Buttons.POWER, short="POWER_TOGGLE"),
                create_btn_mapping(Buttons.VOLUME_UP, short="TEMP_UP"),
                create_btn_mapping(Buttons.VOLUME_DOWN, short="TEMP_DOWN"),
                create_btn_mapping(Buttons.CHANNEL_UP, short="TEMP_UP"),
                create_btn_mapping(Buttons.CHANNEL_DOWN, short="TEMP_DOWN"),
                create_btn_mapping(Buttons.DPAD_UP, short="TEMP_UP"),
                create_btn_mapping(Buttons.DPAD_DOWN, short="TEMP_DOWN"),
                create_btn_mapping(Buttons.HOME, short="RESUME_SCHEDULE"),
            ],
            ui_pages=[
                UiPage("main", "ecobee", grid=Size(4, 6), items=mode_items + [
                    create_ui_text("Temp +", 0, 1, size=Size(2, 1), cmd="TEMP_UP"),
                    create_ui_text("Temp -", 2, 1, size=Size(2, 1), cmd="TEMP_DOWN"),
                    create_ui_text("Home", 0, 2, cmd="PRESET_HOME"),
                    create_ui_text("Away", 1, 2, cmd="PRESET_AWAY"),
                    create_ui_text("Sleep", 2, 2, cmd="PRESET_SLEEP"),
                    create_ui_text("Away ∞", 3, 2, cmd="PRESET_AWAY_INDEFINITELY"),
                    create_ui_text("Resume Schedule", 0, 3, size=Size(4, 1), cmd="RESUME_SCHEDULE"),
                    create_ui_text("Fan Auto", 0, 4, size=Size(2, 1), cmd="FAN_AUTO"),
                    create_ui_text("Fan On", 2, 4, size=Size(2, 1), cmd="FAN_ON"),
                ]),
            ],
            cmd_handler=self._handle_command,
        )
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.available(self._tid):
            state = remote.States.UNAVAILABLE
        else:
            data = self._device.thermostat(self._tid) or {}
            off = data.get("settings", {}).get("hvacMode") == HVAC_OFF
            state = remote.States.OFF if off else remote.States.ON
        self.update({remote.Attributes.STATE: state})

    async def _toggle(self) -> None:
        data = self._device.thermostat(self._tid) or {}
        if data.get("settings", {}).get("hvacMode") == HVAC_OFF:
            await self._device.turn_on(self._tid)
        else:
            await self._device.turn_off(self._tid)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict | None = None, *_a: Any) -> StatusCodes:
        try:
            if cmd_id == remote.Commands.ON:
                await self._device.turn_on(self._tid)
            elif cmd_id == remote.Commands.OFF:
                await self._device.turn_off(self._tid)
            elif cmd_id == remote.Commands.TOGGLE:
                await self._toggle()
            elif cmd_id == remote.Commands.SEND_CMD:
                return await self._run((params or {}).get("command", ""))
            else:
                return StatusCodes.NOT_IMPLEMENTED
            return StatusCodes.OK
        except ValueError as err:
            _LOG.warning("[%s] %s", entity.id, err)
            return StatusCodes.BAD_REQUEST
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Remote command error (%s): %s", entity.id, cmd_id, err)
            return StatusCodes.SERVER_ERROR

    async def _run(self, command: str) -> StatusCodes:
        tid = self._tid
        actions = {
            "POWER_TOGGLE": self._toggle,
            "POWER_ON": lambda: self._device.turn_on(tid),
            "POWER_OFF": lambda: self._device.turn_off(tid),
            "TEMP_UP": lambda: self._device.step_target(tid, 1),
            "TEMP_DOWN": lambda: self._device.step_target(tid, -1),
            "MODE_HEAT": lambda: self._device.set_hvac_mode(tid, HVAC_HEAT),
            "MODE_COOL": lambda: self._device.set_hvac_mode(tid, HVAC_COOL),
            "MODE_AUTO": lambda: self._device.set_hvac_mode(tid, HVAC_AUTO),
            "MODE_OFF": lambda: self._device.set_hvac_mode(tid, HVAC_OFF),
            "PRESET_AWAY_INDEFINITELY": lambda: self._device.set_preset(tid, PRESET_AWAY_INDEFINITELY),
            "RESUME_SCHEDULE": lambda: self._device.set_preset(tid, PRESET_RESUME),
            "FAN_AUTO": lambda: self._device.set_fan_mode(tid, FAN_AUTO),
            "FAN_ON": lambda: self._device.set_fan_mode(tid, FAN_ON),
        }
        if command in COMFORT_COMMANDS:
            await self._device.set_preset(tid, COMFORT_COMMANDS[command])
            return StatusCodes.OK
        if command not in actions:
            return StatusCodes.NOT_IMPLEMENTED
        await actions[command]()
        return StatusCodes.OK


def create_remotes(device_config: EcobeeConfig, device: EcobeeAccount) -> list[EcobeeRemote]:
    return [EcobeeRemote(device_config, device, meta) for meta in device_config.thermostats]
