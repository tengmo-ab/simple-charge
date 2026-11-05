"""Base entity for Simple Charge."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN, NAME
from .coordinator import SimpleChargeCoordinator

VERSION_URL = "https://github.com/tengmo-ab/simple-charge"


class SimpleChargeEntity(CoordinatorEntity[SimpleChargeCoordinator]):
    """All Simple Charge entities hang off one service device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SimpleChargeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.options.get(CONF_NAME) or NAME,
            manufacturer="Simple Charge",
            model="Price planner",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=VERSION_URL,
        )

    @property
    def settings(self) -> dict:
        return self.coordinator.settings
