"""Helper functions for use with IRM KMI integration."""

from irm_kmi_api import RadarStyle

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DARK_MODE, CONF_LANGUAGE_OVERRIDE, CONF_RADAR_STYLE, LANGS


def preferred_language(hass: HomeAssistant, config_entry: ConfigEntry) -> str:
    """Return the language to request from the API."""
    language: str = config_entry.options.get(CONF_LANGUAGE_OVERRIDE, "none")
    if language == "none":
        return hass.config.language if hass.config.language in LANGS else "en"
    return language


def radar_options(config_entry: ConfigEntry) -> tuple[RadarStyle, bool]:
    """Return the radar style and dark mode of a config entry."""
    return (
        RadarStyle(
            config_entry.options.get(CONF_RADAR_STYLE, RadarStyle.OPTION_STYLE_STD)
        ),
        config_entry.options.get(CONF_DARK_MODE, False),
    )
