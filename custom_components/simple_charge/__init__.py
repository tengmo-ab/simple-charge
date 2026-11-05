"""Simple Charge: charge the car in the cheapest quarters of the day."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    ATTR_DURATION,
    ATTR_ENTRY_ID,
    DOMAIN,
    SERVICE_CLEAR_FORCE,
    SERVICE_FORCE_CHARGE,
)
from .coordinator import SimpleChargeConfigEntry, SimpleChargeCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DATETIME,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

FORCE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_DURATION, default=timedelta(hours=1)): cv.positive_time_period,
    }
)
CLEAR_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string})


def _coordinators(hass: HomeAssistant, call: ServiceCall) -> list[SimpleChargeCoordinator]:
    wanted = call.data.get(ATTR_ENTRY_ID)
    found = [
        entry.runtime_data
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if wanted is None or entry.entry_id == wanted
    ]
    if not found:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_entry")
    return found


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services once."""

    async def force_charge(call: ServiceCall) -> None:
        now = dt_util.now()
        for coordinator in _coordinators(hass, call):
            await coordinator.async_force_window(now, now + call.data[ATTR_DURATION])

    async def clear_force(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_force_window(None, None)

    hass.services.async_register(DOMAIN, SERVICE_FORCE_CHARGE, force_charge, FORCE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_FORCE, clear_force, CLEAR_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SimpleChargeConfigEntry) -> bool:
    coordinator = SimpleChargeCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: SimpleChargeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SimpleChargeConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded
