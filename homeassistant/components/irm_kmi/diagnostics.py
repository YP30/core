"""Diagnostics support for the IRM KMI integration."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LOCATION, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant

from .coordinator import IrmKmiConfigEntry

# unique_id and title are the resolved city name
TO_REDACT = {CONF_LOCATION, CONF_UNIQUE_ID, "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: IrmKmiConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = asdict(config_entry.runtime_data.data)

    # Other animation members are URLs carrying the coordinates
    if (animation := data["animation"]) is not None:
        data["animation"] = {"hint": animation["hint"], "unit": animation["unit"]}

    return {
        "config_entry": async_redact_data(config_entry.as_dict(), TO_REDACT),
        "coordinator_data": data,
    }
