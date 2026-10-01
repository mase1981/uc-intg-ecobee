"""Async wrapper around python-ecobee-api (the library used by Home Assistant).

pyecobee is synchronous (requests), so every call runs in a worker thread and
calls are serialised with a lock because the library mutates shared state
(thermostat list and tokens).
"""

import asyncio
import logging
from typing import Any, Callable

from pyecobee import (
    ECOBEE_API_KEY,
    ECOBEE_PASSWORD,
    ECOBEE_REFRESH_TOKEN,
    ECOBEE_USERNAME,
    Ecobee,
    EcobeeAuthFailedError,
    EcobeeAuthMfaRequiredError,
    EcobeeAuthUnknownError,
    ExpiredTokenError,
    InvalidTokenError,
    MfaChallenge,
)

_LOG = logging.getLogger(__name__)


class AuthRequiredError(Exception):
    """The stored credentials/tokens no longer work - setup must be re-run."""


class EcobeeClient:
    """One ecobee account."""

    def __init__(
        self,
        api_key: str = "",
        username: str = "",
        password: str = "",
        refresh_token: str = "",
    ) -> None:
        config: dict[str, Any] = {}
        if api_key:
            config[ECOBEE_API_KEY] = api_key
        else:
            config[ECOBEE_USERNAME] = username
            config[ECOBEE_PASSWORD] = password
        if refresh_token:
            config[ECOBEE_REFRESH_TOKEN] = refresh_token
        self.ecobee = Ecobee(config=config)
        self._lock = asyncio.Lock()

    @property
    def uses_api_key(self) -> bool:
        return bool(self.ecobee.api_key)

    @property
    def refresh_token(self) -> str:
        return self.ecobee.refresh_token or ""

    @property
    def pin(self) -> str:
        return self.ecobee.pin or ""

    @property
    def thermostats(self) -> list[dict]:
        return self.ecobee.thermostats or []

    async def _run(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            return await asyncio.to_thread(func, *args, **kwargs)

    # -- authentication ------------------------------------------------
    async def login(self) -> bool:
        """Credential login. Raises EcobeeAuthMfaRequiredError when MFA is needed."""
        self.ecobee.refresh_token = None
        return bool(await self._run(self.ecobee.refresh_tokens))

    async def submit_mfa_code(self, challenge: MfaChallenge, code: str) -> bool:
        return bool(await self._run(self.ecobee.submit_mfa_code, challenge, code))

    async def request_pin(self) -> bool:
        return bool(await self._run(self.ecobee.request_pin))

    async def request_tokens(self) -> bool:
        return bool(await self._run(self.ecobee.request_tokens))

    async def refresh(self) -> bool:
        """Refresh the access token; fall back to a full login with stored credentials."""
        try:
            # False here means a transient failure (network / server error).
            return bool(await self._run(self.ecobee.refresh_tokens))
        except InvalidTokenError:
            _LOG.info("ecobee refresh token rejected")
        except EcobeeAuthUnknownError as err:
            _LOG.warning("ecobee token refresh failed: %s", err)
            return False
        except (EcobeeAuthFailedError, EcobeeAuthMfaRequiredError) as err:
            raise AuthRequiredError(str(err)) from err

        if self.uses_api_key or not (self.ecobee.username and self.ecobee.password):
            raise AuthRequiredError("ecobee authorization expired - re-run setup")
        try:
            return await self.login()
        except (EcobeeAuthFailedError, EcobeeAuthMfaRequiredError, InvalidTokenError) as err:
            raise AuthRequiredError(f"ecobee login failed: {err}") from err
        except EcobeeAuthUnknownError as err:
            _LOG.warning("ecobee login failed: %s", err)
            return False

    # -- data ----------------------------------------------------------
    async def update(self) -> bool:
        """Fetch all thermostats. Refreshes tokens once on expiry."""
        try:
            return bool(await self._run(self.ecobee.update))
        except (ExpiredTokenError, InvalidTokenError):
            if not await self.refresh():
                return False
            return bool(await self._run(self.ecobee.update))

    def index_of(self, thermostat_id: str) -> int | None:
        for index, thermostat in enumerate(self.thermostats):
            if str(thermostat.get("identifier")) == str(thermostat_id):
                return index
        return None

    async def call(self, method: str, thermostat_id: str, *args: Any, **kwargs: Any) -> None:
        """Run a pyecobee setter (e.g. ``set_hvac_mode``) for one thermostat."""
        index = self.index_of(thermostat_id)
        if index is None:
            raise ValueError(f"Unknown thermostat {thermostat_id}")
        func = getattr(self.ecobee, method)
        try:
            await self._run(func, index, *args, **kwargs)
        except (ExpiredTokenError, InvalidTokenError):
            if not await self.refresh():
                raise
            await self._run(func, index, *args, **kwargs)
