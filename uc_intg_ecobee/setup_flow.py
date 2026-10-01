"""Setup flow: ecobee account login (email + password, with MFA) or legacy API key + PIN.

Mirrors the Home Assistant ecobee config flow. The extra screens (MFA code, PIN
authorization) are answered through the manual-entry step, so query_device()
routes on the current stage.
"""

import hashlib
import logging
from typing import Any

from pyecobee import EcobeeAuthFailedError, EcobeeAuthMfaRequiredError, EcobeeAuthUnknownError, MfaChallenge
from ucapi import IntegrationSetupError, RequestUserInput, SetupError
from ucapi_framework import BaseSetupFlow

from uc_intg_ecobee import thermostat as tstat
from uc_intg_ecobee.client import EcobeeClient
from uc_intg_ecobee.config import EcobeeConfig
from uc_intg_ecobee.const import AUTH_API_KEY, AUTH_CREDENTIALS, ECOBEE_AUTH_URL

_LOG = logging.getLogger(__name__)

STAGE_NONE = ""
STAGE_MFA = "mfa"
STAGE_PIN = "pin"


class EcobeeSetupFlow(BaseSetupFlow[EcobeeConfig]):
    """Sign in to ecobee and add all thermostats of the account."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._reset()

    def _reset(self) -> None:
        self._stage = STAGE_NONE
        self._client: EcobeeClient | None = None
        self._challenge: MfaChallenge | None = None
        self._username = ""
        self._password = ""
        self._api_key = ""

    def get_manual_entry_form(self) -> RequestUserInput:
        self._reset()
        return RequestUserInput(
            {"en": "ecobee Sign In"},
            [
                {
                    "id": "info",
                    "label": {"en": "ecobee Account"},
                    "field": {"label": {"value": {"en": (
                        "Sign in with the email and password of your ecobee account (the same as the "
                        "ecobee app). If your account uses two-step verification you will be asked for "
                        "the code next. Leave the API key empty unless you have a legacy ecobee "
                        "developer API key - in that case leave email and password empty instead."
                    )}}},
                },
                {"id": "username", "label": {"en": "Email"}, "field": {"text": {"value": ""}}},
                {"id": "password", "label": {"en": "Password"}, "field": {"password": {"value": ""}}},
                {"id": "api_key", "label": {"en": "Developer API key (optional, legacy)"},
                 "field": {"text": {"value": ""}}},
            ],
        )

    async def query_device(self, input_values: dict[str, Any]) -> EcobeeConfig | RequestUserInput | SetupError:
        if self._stage == STAGE_MFA and "mfa_code" in input_values:
            return await self._handle_mfa(str(input_values.get("mfa_code", "")).strip())
        if self._stage == STAGE_PIN and "username" not in input_values:
            return await self._handle_pin()

        self._reset()
        self._username = str(input_values.get("username", "")).strip()
        self._password = str(input_values.get("password", ""))
        self._api_key = str(input_values.get("api_key", "")).strip()

        if self._api_key and not (self._username or self._password):
            return await self._start_pin()
        if self._username and self._password and not self._api_key:
            return await self._start_login()
        _LOG.warning("Enter either email + password, or a developer API key - not both")
        return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)

    # -- email + password ----------------------------------------------
    async def _start_login(self) -> EcobeeConfig | RequestUserInput | SetupError:
        self._client = EcobeeClient(username=self._username, password=self._password)
        try:
            if not await self._client.login():
                return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)
        except EcobeeAuthMfaRequiredError as err:
            self._challenge = err.args[0]
            self._stage = STAGE_MFA
            return self._mfa_screen()
        except EcobeeAuthFailedError:
            _LOG.warning("ecobee rejected the email or password")
            return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)
        except EcobeeAuthUnknownError as err:
            _LOG.error("ecobee login failed: %s", err)
            return SetupError(IntegrationSetupError.OTHER)
        return await self._finish(AUTH_CREDENTIALS)

    def _mfa_screen(self) -> RequestUserInput:
        mfa_type = getattr(self._challenge, "mfa_type", "") or "verification"
        return RequestUserInput(
            {"en": "ecobee Verification Code"},
            [
                {
                    "id": "mfa_info",
                    "label": {"en": "Two-step verification"},
                    "field": {"label": {"value": {"en": (
                        f"ecobee requires a {mfa_type} verification code for this account. Enter the "
                        "code from your authenticator app or text message."
                    )}}},
                },
                {"id": "mfa_code", "label": {"en": "Verification code"}, "field": {"text": {"value": ""}}},
            ],
        )

    async def _handle_mfa(self, code: str) -> EcobeeConfig | RequestUserInput | SetupError:
        if self._client is None or self._challenge is None:
            return SetupError(IntegrationSetupError.OTHER)
        if not code:
            return self._mfa_screen()
        try:
            if not await self._client.submit_mfa_code(self._challenge, code):
                return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)
        except EcobeeAuthFailedError:
            _LOG.warning("ecobee rejected the verification code")
            return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)
        except EcobeeAuthUnknownError as err:
            _LOG.error("ecobee verification failed: %s", err)
            return SetupError(IntegrationSetupError.OTHER)
        return await self._finish(AUTH_CREDENTIALS)

    # -- legacy developer API key + PIN --------------------------------
    async def _start_pin(self) -> RequestUserInput | SetupError:
        self._client = EcobeeClient(api_key=self._api_key)
        if not await self._client.request_pin():
            _LOG.warning("ecobee did not issue a PIN - check the API key")
            return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)
        self._stage = STAGE_PIN
        return RequestUserInput(
            {"en": "Authorize on ecobee.com"},
            [
                {
                    "id": "pin_info",
                    "label": {"en": f"PIN: {self._client.pin}"},
                    "field": {"label": {"value": {"en": (
                        f"Go to {ECOBEE_AUTH_URL}, sign in, open My Apps -> Add Application, enter "
                        f"the PIN {self._client.pin} and click Authorize. Then press Next here."
                    )}}},
                },
                {"id": "pin_done", "label": {"en": "I have authorized the PIN"},
                 "field": {"checkbox": {"value": False}}},
            ],
        )

    async def _handle_pin(self) -> EcobeeConfig | SetupError:
        if self._client is None:
            return SetupError(IntegrationSetupError.OTHER)
        if not await self._client.request_tokens():
            _LOG.warning("ecobee PIN not authorized yet (or expired)")
            return SetupError(IntegrationSetupError.AUTHORIZATION_ERROR)
        return await self._finish(AUTH_API_KEY)

    # -- common --------------------------------------------------------
    async def _finish(self, auth_mode: str) -> EcobeeConfig | SetupError:
        assert self._client is not None
        if not await self._client.update() or not self._client.thermostats:
            _LOG.error("No ecobee thermostats found on this account")
            return SetupError(IntegrationSetupError.NOT_FOUND)

        meta = [tstat.build_meta(t) for t in self._client.thermostats]
        account_key = (self._username.lower() if auth_mode == AUTH_CREDENTIALS else self._api_key)
        identifier = "ecobee_" + hashlib.sha1(account_key.encode()).hexdigest()[:10]
        names = ", ".join(m["name"] for m in meta)
        _LOG.info("ecobee setup found %d thermostat(s): %s", len(meta), names)

        config = EcobeeConfig(
            identifier=identifier,
            name="ecobee" if len(meta) > 1 else f"ecobee {meta[0]['name']}",
            auth_mode=auth_mode,
            username=self._username if auth_mode == AUTH_CREDENTIALS else "",
            password=self._password if auth_mode == AUTH_CREDENTIALS else "",
            api_key=self._api_key if auth_mode == AUTH_API_KEY else "",
            refresh_token=self._client.refresh_token,
            thermostats=meta,
        )
        self._reset()
        return config
