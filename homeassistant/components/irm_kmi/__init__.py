"""Integration for IRM KMI weather."""

from irm_kmi_api import IrmKmiApiClientHa

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, IRM_KMI_TO_HA_CONDITION_MAP, PLATFORMS, USER_AGENT
from .coordinator import IrmKmiConfigEntry, IrmKmiCoordinator
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the IRM KMI integration."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: IrmKmiConfigEntry) -> bool:
    """Set up this integration using UI."""
    api_client = IrmKmiApiClientHa(
        session=async_get_clientsession(hass),
        user_agent=USER_AGENT,
        cdt_map=IRM_KMI_TO_HA_CONDITION_MAP,
    )

    entry.runtime_data = IrmKmiCoordinator(hass, entry, api_client)

    await entry.runtime_data.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: IrmKmiConfigEntry) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
