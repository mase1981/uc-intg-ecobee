"""Configuration dataclass and manager for the ecobee integration."""

from dataclasses import dataclass, field
from typing import Any

from ucapi_framework import BaseConfigManager


@dataclass
class EcobeeConfig:
    """Configuration for one ecobee account (all its thermostats)."""

    identifier: str = ""
    name: str = ""
    auth_mode: str = "credentials"  # "credentials" or "api_key"
    username: str = ""
    password: str = ""
    api_key: str = ""
    refresh_token: str = ""
    # Thermostat metadata captured at setup so entities exist even while the
    # ecobee cloud is unreachable. See thermostat.build_meta().
    thermostats: list[dict[str, Any]] = field(default_factory=list)


class EcobeeConfigManager(BaseConfigManager[EcobeeConfig]):
    """Config manager bound to :class:`EcobeeConfig`."""
