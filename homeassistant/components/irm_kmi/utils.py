"""Helper functions for use with IRM KMI integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_LANGUAGE_OVERRIDE, LANGS


def preferred_language(hass: HomeAssistant, config_entry: ConfigEntry) -> str:
    """Return the language to request from the API."""
    language: str = config_entry.options.get(CONF_LANGUAGE_OVERRIDE, "none")
    if language == "none":
        return hass.config.language if hass.config.language in LANGS else "en"
    return language
