"""Helper functions for use with IRM KMI integration."""

from irm_kmi_api import RadarForecast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import CONF_LANGUAGE_OVERRIDE, LANGS


def preferred_language(hass: HomeAssistant, config_entry: ConfigEntry) -> str:
    """Return the language to request from the API."""
    language: str = config_entry.options.get(CONF_LANGUAGE_OVERRIDE, "none")
    if language == "none":
        return hass.config.language if hass.config.language in LANGS else "en"
    return language


def current_radar_frame(radar_forecast: list[RadarForecast]) -> int:
    """Return the index of the last radar frame at or before now, clamped to 0."""
    now = dt_util.utcnow()
    started = sum(
        dt_util.parse_datetime(forecast["datetime"], raise_on_error=True) <= now
        for forecast in radar_forecast
    )
    return max(started - 1, 0)
