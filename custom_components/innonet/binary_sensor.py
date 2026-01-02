"""Binary sensor platform for INNOnet."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import InnonetDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up INNOnet binary sensors."""
    coordinator: InnonetDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([InnonetSunWindowActiveSensor(coordinator, entry)])


class InnonetSunWindowActiveSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary Sensor representing if Sun Window is currently active."""

    def __init__(self, coordinator: InnonetDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.data['zpn']}_sun_window_active"
        self._attr_has_entity_name = True
        self._attr_name = "Sun Window Active"
        # Used 'power' as it relates to grid/power status, or generic (None)
        # 'running' or 'plug' are also options, but 'power' is okay.
        # Actually, let's leave device_class empty for generic On/Off or use 'opening' if it were a window :)
        # 'battery_charging' is also semantically close for what people do with it.
        # Let's use None for generic.
        self._attr_device_class = None 
        self._attr_icon = "mdi:white-balance-sunny"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["zpn"])},
            name="INNOnet Service",
            manufacturer="INNOnet",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on (Sun Window Active)."""
        return self.coordinator.data.get("sun_window_active")