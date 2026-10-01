"""Integration driver for ecobee thermostats."""

from ucapi_framework import BaseIntegrationDriver

from uc_intg_ecobee.climate import create_climates
from uc_intg_ecobee.config import EcobeeConfig
from uc_intg_ecobee.device import EcobeeAccount
from uc_intg_ecobee.remote import create_remotes
from uc_intg_ecobee.select import create_selects
from uc_intg_ecobee.sensor import create_sensors
from uc_intg_ecobee.switch import create_switches


class EcobeeDriver(BaseIntegrationDriver[EcobeeAccount, EcobeeConfig]):
    """Builds entities for every thermostat of an ecobee account.

    Thermostat metadata is stored in the config at setup, so entities are
    registered without waiting for the ecobee cloud.
    """

    def __init__(self) -> None:
        super().__init__(
            device_class=EcobeeAccount,
            entity_classes=[
                create_climates,
                create_remotes,
                create_selects,
                create_switches,
                create_sensors,
            ],
            driver_id="ecobee",
            require_connection_before_registry=False,
        )
