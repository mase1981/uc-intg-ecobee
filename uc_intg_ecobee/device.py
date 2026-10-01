"""ecobee account device - polls all thermostats of one ecobee account.

ecobee is cloud-only. Tokens are refreshed on connect (like Home Assistant)
and a rotated refresh token is written back to the config so a restart never
needs a new login. Commands are followed by an immediate refresh so the Remote
shows the new state without waiting for the 3-minute poll.
"""

import asyncio
import logging
from typing import Any

from ucapi_framework import PollingDevice

from uc_intg_ecobee import thermostat as tstat
from uc_intg_ecobee.client import AuthRequiredError, EcobeeClient
from uc_intg_ecobee.config import EcobeeConfig
from uc_intg_ecobee.const import (
    AUTH_API_KEY,
    FAN_AUTO,
    FAN_ON,
    HUMIDIFIER_MODES,
    HVAC_AUTO,
    HVAC_AUX_HEAT_ONLY,
    HVAC_COOL,
    HVAC_HEAT,
    HVAC_OFF,
    POLL_INTERVAL,
    PRESET_AWAY_INDEFINITELY,
    PRESET_RESUME,
    PRESET_TEMPERATURE,
    PRESET_VACATION,
    STATE_AUTH_REQUIRED,
    STATE_ON,
    STATE_UNAVAILABLE,
)

_LOG = logging.getLogger(__name__)


class EcobeeAccount(PollingDevice):
    """One ecobee account with one or more thermostats."""

    def __init__(self, device_config: EcobeeConfig, **kwargs: Any) -> None:
        super().__init__(device_config, poll_interval=POLL_INTERVAL, **kwargs)
        self._device_config = device_config
        self._client: EcobeeClient | None = None
        self._state: str = STATE_UNAVAILABLE
        self._last_active_mode: dict[str, str] = {}
        self._mode_before_aux: dict[str, str] = {}

    # -- identity ------------------------------------------------------
    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str:
        return "ecobee-cloud"

    @property
    def log_id(self) -> str:
        return f"{self.name} (ecobee)"

    @property
    def state(self) -> str:
        return self._state

    def meta(self, thermostat_id: str) -> dict[str, Any]:
        return next((m for m in self._device_config.thermostats if m.get("id") == thermostat_id), {})

    def thermostat(self, thermostat_id: str) -> dict | None:
        if self._client is None or self._state != STATE_ON:
            return None
        index = self._client.index_of(thermostat_id)
        return None if index is None else self._client.thermostats[index]

    def available(self, thermostat_id: str) -> bool:
        data = self.thermostat(thermostat_id)
        return bool(data and data.get("runtime", {}).get("connected", False))

    # -- connection lifecycle ------------------------------------------
    def _new_client(self) -> EcobeeClient:
        cfg = self._device_config
        if cfg.auth_mode == AUTH_API_KEY:
            return EcobeeClient(api_key=cfg.api_key, refresh_token=cfg.refresh_token)
        return EcobeeClient(username=cfg.username, password=cfg.password, refresh_token=cfg.refresh_token)

    async def establish_connection(self) -> EcobeeClient:
        self._client = self._new_client()
        try:
            if await self._client.refresh():
                await self._update()
            else:
                _LOG.warning("[%s] ecobee cloud not reachable yet - will retry", self.log_id)
                self._state = STATE_UNAVAILABLE
        except AuthRequiredError as err:
            self._auth_required(err)
        self._persist_token()
        self.push_update()
        return self._client

    def _auth_required(self, err: Exception) -> None:
        _LOG.error(
            "[%s] ecobee authorization failed (%s). Re-run the integration setup to sign in again.",
            self.log_id,
            err,
        )
        self._state = STATE_AUTH_REQUIRED

    async def poll_device(self) -> None:
        if self._client is None or self._state == STATE_AUTH_REQUIRED:
            # Don't hammer ecobee with failing logins (account lockout).
            return
        try:
            await self._update()
        except AuthRequiredError as err:
            self._auth_required(err)
        self._persist_token()
        self.push_update()

    async def _update(self) -> None:
        assert self._client is not None
        if await self._client.update() and self._client.thermostats:
            if self._state != STATE_ON:
                _LOG.info("[%s] Connected - %d thermostat(s)", self.log_id, len(self._client.thermostats))
            self._state = STATE_ON
            for data in self._client.thermostats:
                mode = tstat.hvac_mode(data)
                if mode not in (HVAC_OFF, HVAC_AUX_HEAT_ONLY):
                    self._last_active_mode[str(data.get("identifier"))] = mode
            self._sync_meta()
        else:
            if self._state == STATE_ON:
                _LOG.warning("[%s] ecobee update failed - marking unavailable", self.log_id)
            self._state = STATE_UNAVAILABLE

    def _sync_meta(self) -> None:
        assert self._client is not None
        meta = [tstat.build_meta(t) for t in self._client.thermostats]
        if meta != self._device_config.thermostats:
            old_ids = {m.get("id") for m in self._device_config.thermostats}
            if {m["id"] for m in meta} != old_ids:
                _LOG.info("[%s] Thermostat list changed - restart the integration to update entities", self.log_id)
            self.update_config(thermostats=meta)

    def _persist_token(self) -> None:
        if self._client is None:
            return
        token = self._client.refresh_token
        if token and token != self._device_config.refresh_token:
            self.update_config(refresh_token=token)

    async def disconnect(self) -> None:
        self._client = None
        self._state = STATE_UNAVAILABLE
        await super().disconnect()

    # -- command plumbing ----------------------------------------------
    def _require(self, thermostat_id: str) -> dict:
        data = self.thermostat(thermostat_id)
        if data is None:
            raise ConnectionError("ecobee thermostat not available")
        return data

    async def _call(self, method: str, thermostat_id: str, *args: Any, **kwargs: Any) -> None:
        assert self._client is not None
        try:
            await self._client.call(method, thermostat_id, *args, **kwargs)
        except AuthRequiredError as err:
            self._auth_required(err)
            self.push_update()
            raise
        await self.refresh_now()
        if self._state != STATE_ON:
            # pyecobee logs request failures instead of raising; the refresh tells us.
            raise ConnectionError("ecobee cloud not reachable")

    async def refresh_now(self) -> None:
        """Fetch fresh state right after a command."""
        await asyncio.sleep(1)
        try:
            await self._update()
        except AuthRequiredError as err:
            self._auth_required(err)
        self._persist_token()
        self.push_update()

    def _clamp_f(self, thermostat_id: str, value_f: float) -> float:
        meta = self.meta(thermostat_id)
        return max(meta.get("min_f", 45.0), min(meta.get("max_f", 92.0), value_f))

    # -- hvac mode / power ---------------------------------------------
    async def set_hvac_mode(self, thermostat_id: str, mode: str) -> None:
        self._require(thermostat_id)
        await self._call("set_hvac_mode", thermostat_id, mode)

    def default_on_mode(self, thermostat_id: str) -> str:
        if thermostat_id in self._last_active_mode:
            return self._last_active_mode[thermostat_id]
        meta = self.meta(thermostat_id)
        if meta.get("heat") and meta.get("cool"):
            return HVAC_AUTO
        return HVAC_COOL if meta.get("cool") else HVAC_HEAT

    async def turn_on(self, thermostat_id: str) -> None:
        await self.set_hvac_mode(thermostat_id, self.default_on_mode(thermostat_id))

    async def turn_off(self, thermostat_id: str) -> None:
        await self.set_hvac_mode(thermostat_id, HVAC_OFF)

    async def set_aux_heat(self, thermostat_id: str, enabled: bool) -> None:
        data = self._require(thermostat_id)
        current = tstat.hvac_mode(data)
        if enabled:
            if current != HVAC_AUX_HEAT_ONLY:
                self._mode_before_aux[thermostat_id] = current
            await self.set_hvac_mode(thermostat_id, HVAC_AUX_HEAT_ONLY)
        else:
            await self.set_hvac_mode(thermostat_id, self._mode_before_aux.get(thermostat_id, HVAC_HEAT))

    # -- temperatures --------------------------------------------------
    async def _hold_temps(self, thermostat_id: str, heat_f: float, cool_f: float) -> None:
        data = self._require(thermostat_id)
        delta = tstat.min_delta_f(data)
        heat_f = self._clamp_f(thermostat_id, heat_f)
        cool_f = self._clamp_f(thermostat_id, cool_f)
        if tstat.hvac_mode(data) == HVAC_AUTO and cool_f - heat_f < delta:
            cool_f = heat_f + delta
        hold_type, hold_hours = tstat.hold_params(data)
        args: list[Any] = [round(cool_f, 1), round(heat_f, 1), hold_type]
        if hold_hours is not None:
            args.append(hold_hours)
        await self._call("set_hold_temp", thermostat_id, *args)

    async def set_target(self, thermostat_id: str, value: float) -> None:
        """Set the target in the display unit. In auto mode the range is shifted."""
        data = self._require(thermostat_id)
        target_f = tstat.from_display(value, self.meta(thermostat_id).get("celsius", False))
        mode = tstat.hvac_mode(data)
        heat_f, cool_f = tstat.setpoints_f(data)
        if mode == HVAC_AUTO:
            shift = target_f - (heat_f + cool_f) / 2
            await self._hold_temps(thermostat_id, heat_f + shift, cool_f + shift)
        elif tstat.is_heat_mode(mode):
            await self._hold_temps(thermostat_id, target_f, max(cool_f, target_f))
        elif mode == HVAC_COOL:
            await self._hold_temps(thermostat_id, min(heat_f, target_f), target_f)
        else:
            # Off: ecobee recommends identical heat/cool hold values outside auto.
            await self._hold_temps(thermostat_id, target_f, target_f)

    async def set_range(self, thermostat_id: str, low: float, high: float) -> None:
        celsius = self.meta(thermostat_id).get("celsius", False)
        await self._hold_temps(thermostat_id, tstat.from_display(low, celsius), tstat.from_display(high, celsius))

    async def step_target(self, thermostat_id: str, steps: int) -> None:
        """Nudge the target by ``steps`` display units (1 °F or 0.5 °C each)."""
        current = self.target(thermostat_id)
        if current is None:
            return
        celsius = self.meta(thermostat_id).get("celsius", False)
        await self.set_target(thermostat_id, current + steps * (0.5 if celsius else 1.0))

    def target(self, thermostat_id: str) -> float | None:
        """Target temperature in display unit (midpoint of the range in auto mode)."""
        data = self.thermostat(thermostat_id)
        if data is None:
            return None
        celsius = self.meta(thermostat_id).get("celsius", False)
        mode = tstat.hvac_mode(data)
        heat_f, cool_f = tstat.setpoints_f(data)
        if tstat.is_heat_mode(mode):
            return tstat.to_display(heat_f, celsius)
        if mode == HVAC_COOL:
            return tstat.to_display(cool_f, celsius)
        if mode == HVAC_AUTO:
            return tstat.to_display((heat_f + cool_f) / 2, celsius)
        return None

    # -- presets -------------------------------------------------------
    def preset_options(self, thermostat_id: str) -> list[str]:
        data = self.thermostat(thermostat_id)
        if data is None:
            return []
        options = list(tstat.comfort_settings(data).values())
        options += [PRESET_AWAY_INDEFINITELY, PRESET_RESUME]
        current, _ = tstat.preset(data)
        if current and current not in options:
            options.insert(0, current)
        return options

    async def set_preset(self, thermostat_id: str, label: str) -> None:
        data = self._require(thermostat_id)
        current, vacation = tstat.preset(data)
        if label == current:
            return
        if label == PRESET_VACATION:
            raise ValueError("Vacations are created in the ecobee app")
        if current == PRESET_VACATION and vacation:
            await self._call("delete_vacation", thermostat_id, vacation)
            data = self._require(thermostat_id)
        hold_type, hold_hours = tstat.hold_params(data)
        if label == PRESET_RESUME:
            await self._call("resume_program", thermostat_id)
        elif label == PRESET_AWAY_INDEFINITELY:
            await self._call("set_climate_hold", thermostat_id, "away", "indefinite", hold_hours)
        elif label == PRESET_TEMPERATURE:
            heat_f, cool_f = tstat.setpoints_f(data)
            await self._hold_temps(thermostat_id, heat_f, cool_f)
        else:
            ref = next((r for r, n in tstat.comfort_settings(data).items() if n == label), None)
            if ref is None:
                raise ValueError(f"Unknown preset {label}")
            await self._call("set_climate_hold", thermostat_id, ref, hold_type, hold_hours)

    # -- fan / humidity / ventilator -----------------------------------
    async def set_fan_mode(self, thermostat_id: str, fan_mode: str) -> None:
        if fan_mode not in (FAN_AUTO, FAN_ON):
            raise ValueError(f"Invalid fan mode {fan_mode}")
        data = self._require(thermostat_id)
        heat_f, cool_f = tstat.setpoints_f(data)
        hold_type, hold_hours = tstat.hold_params(data)
        # ecobee ignores a fan-only hold unless the setpoints are included (see HA).
        kwargs: dict[str, Any] = {"coolHoldTemp": cool_f, "heatHoldTemp": heat_f}
        if hold_hours is not None:
            kwargs["holdHours"] = hold_hours
        await self._call("set_fan_mode", thermostat_id, fan_mode, hold_type, **kwargs)

    async def set_fan_min_on_time(self, thermostat_id: str, minutes: int) -> None:
        await self._call("set_fan_min_on_time", thermostat_id, max(0, min(60, int(minutes))))

    async def set_humidifier_mode(self, thermostat_id: str, mode: str) -> None:
        if mode not in HUMIDIFIER_MODES:
            raise ValueError(f"Invalid humidifier mode {mode}")
        await self._call("set_humidifier_mode", thermostat_id, mode)

    async def set_humidity(self, thermostat_id: str, humidity: int) -> None:
        await self._call("set_humidity", thermostat_id, max(0, min(100, int(humidity))))

    async def set_ventilator_timer(self, thermostat_id: str, enabled: bool) -> None:
        await self._call("set_ventilator_timer", thermostat_id, enabled)
