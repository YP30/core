"""Tests for the IRM KMI weather platform."""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

from irm_kmi_api import ExtendedForecast
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.irm_kmi.const import CONF_LANGUAGE_OVERRIDE
from homeassistant.components.weather import (
    DOMAIN as WEATHER_DOMAIN,
    SERVICE_GET_FORECASTS,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.entity_registry as er

from . import setup_integration
from .const import WEATHER_ENTITY_ID

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture(autouse=True)
def override_platforms() -> Generator[None]:
    """Load only the weather platform."""
    with patch("homeassistant.components.irm_kmi.PLATFORMS", [Platform.WEATHER]):
        yield


async def _get_forecast(
    hass: HomeAssistant, forecast_type: str
) -> list[dict[str, Any]]:
    """Return the forecast from weather.get_forecasts."""
    response = await hass.services.async_call(
        WEATHER_DOMAIN,
        SERVICE_GET_FORECASTS,
        {
            ATTR_ENTITY_ID: WEATHER_ENTITY_ID,
            "type": forecast_type,
        },
        blocking=True,
        return_response=True,
    )
    return response[WEATHER_ENTITY_ID]["forecast"]


@pytest.mark.usefixtures("mock_get_forecasts_coord")
@pytest.mark.parametrize("forecast_fixture", ["forecast_nl.json"])
@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
async def test_weather_nl(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test weather with forecast from the Netherland."""
    await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("mock_get_forecasts_coord")
@pytest.mark.parametrize("forecast_fixture", ["forecast_nl.json"])
@pytest.mark.parametrize(
    "forecast_type",
    ["daily", "twice_daily", "hourly"],
)
@pytest.mark.freeze_time("2025-09-22T15:30:00+01:00")
async def test_forecast_service(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    forecast_type: str,
) -> None:
    """Test multiple forecast."""
    await setup_integration(hass, mock_config_entry)

    assert await _get_forecast(hass, forecast_type) == snapshot


@pytest.mark.usefixtures("mock_get_forecasts_coord")
@pytest.mark.parametrize(
    ("hass_language", "options", "expected_text"),
    [
        pytest.param("en", {}, "Hey!", id="english"),
        pytest.param("en", {CONF_LANGUAGE_OVERRIDE: "fr"}, "Bar", id="override_fr"),
        pytest.param("en", {CONF_LANGUAGE_OVERRIDE: "nl"}, "Foo", id="override_nl"),
        pytest.param(
            "nl",
            {CONF_LANGUAGE_OVERRIDE: "none"},
            "Foo",
            id="follow_home_assistant",
        ),
        pytest.param("nl", {}, "Foo", id="follow_home_assistant_by_default"),
    ],
)
@pytest.mark.freeze_time("2024-01-23T14:15:00+01:00")
async def test_forecast_language(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    hass_language: str,
    options: dict[str, str],
    expected_text: str,
) -> None:
    """Test the forecast text is fetched in the language the user asked for."""
    hass.config.language = hass_language
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(mock_config_entry, options=options)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Only the second recorded day carries a text in every language
    assert (await _get_forecast(hass, "daily"))[1]["text"] == expected_text


@pytest.mark.usefixtures("mock_get_forecasts_coord")
@pytest.mark.parametrize("forecast_fixture", ["high_low_temp.json"])
@pytest.mark.freeze_time("2024-01-21T14:15:00+01:00")
async def test_forecasts_do_not_mutate_coordinator_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test reading the daily forecast does not change the twice daily forecast."""
    await setup_integration(hass, mock_config_entry)

    twice_daily = await _get_forecast(hass, "twice_daily")
    await _get_forecast(hass, "daily")

    assert await _get_forecast(hass, "twice_daily") == twice_daily


@pytest.mark.parametrize(
    ("daily_forecast", "expected"),
    [
        pytest.param(
            [
                ExtendedForecast(
                    datetime="2024-01-21",
                    is_daytime=False,
                    native_temperature=None,
                    native_templow=2.0,
                ),
                ExtendedForecast(
                    datetime="2024-01-22",
                    is_daytime=True,
                    native_temperature=8.0,
                    native_templow=None,
                ),
            ],
            [(None, 2.0), (8.0, 2.0)],
            id="borrowed_low",
        ),
        pytest.param(
            [
                ExtendedForecast(
                    datetime="2024-01-21",
                    is_daytime=False,
                    native_temperature=None,
                    native_templow=12.0,
                ),
                ExtendedForecast(
                    datetime="2024-01-22",
                    is_daytime=True,
                    native_temperature=8.0,
                    native_templow=None,
                ),
            ],
            [(None, 12.0), (12.0, 8.0)],
            id="borrowed_low_swapped",
        ),
    ],
)
async def test_daily_forecast_starting_at_night(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_irm_kmi_api: MagicMock,
    daily_forecast: list[ExtendedForecast],
    expected: list[tuple[float | None, float | None]],
) -> None:
    """Test a daily forecast starting at night keeps the night entry."""
    mock_irm_kmi_api.get_daily_forecast.return_value = daily_forecast
    await setup_integration(hass, mock_config_entry)

    assert [
        (forecast.get("temperature"), forecast.get("templow"))
        for forecast in await _get_forecast(hass, "daily")
    ] == expected
