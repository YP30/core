"""Tests for the IRM KMI config flow."""

from unittest.mock import AsyncMock

from irm_kmi_api import IrmKmiApiError, RadarStyle
import pytest

from homeassistant.components.irm_kmi.const import (
    CONF_DARK_MODE,
    CONF_LANGUAGE_OVERRIDE,
    CONF_LANGUAGE_OVERRIDE_OPTIONS,
    CONF_RADAR_STYLE,
    CONF_RADAR_STYLE_OPTIONS,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_LOCATION,
    CONF_UNIQUE_ID,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations

from tests.common import MockConfigEntry, async_load_json_object_fixture


@pytest.mark.usefixtures("mock_setup_entry", "mock_config_flow_forecast")
async def test_full_user_flow(hass: HomeAssistant) -> None:
    """Test the full user configuration flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 50.123, ATTR_LONGITUDE: 4.456}},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Brussels"
    assert result["data"] == {
        CONF_LOCATION: {ATTR_LATITUDE: 50.123, ATTR_LONGITUDE: 4.456},
        CONF_UNIQUE_ID: "brussels be",
    }
    assert result["result"].unique_id == "brussels be"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_config_flow_location_out_benelux(
    hass: HomeAssistant, mock_config_flow_forecast: AsyncMock
) -> None:
    """Test configuration flow with a location outside of Benelux."""
    in_benelux = mock_config_flow_forecast.return_value
    mock_config_flow_forecast.return_value = await async_load_json_object_fixture(
        hass, "forecast_out_of_benelux.json", DOMAIN
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 0.123, ATTR_LONGITUDE: 0.456}},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_LOCATION: "out_of_benelux"}

    mock_config_flow_forecast.return_value = in_benelux
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 50.123, ATTR_LONGITUDE: 4.456}},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Brussels"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_config_flow_with_api_error(
    hass: HomeAssistant, mock_config_flow_forecast: AsyncMock
) -> None:
    """Test the flow recovers from an API error."""
    mock_config_flow_forecast.side_effect = IrmKmiApiError
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 50.123, ATTR_LONGITUDE: 4.456}},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_config_flow_forecast.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 50.123, ATTR_LONGITUDE: 4.456}},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_setup_entry", "mock_config_flow_forecast")
async def test_setup_twice_same_location(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the flow aborts when the location is already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 50.5, ATTR_LONGITUDE: 4.6}},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_option_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test when the user changes options with the option flow."""
    mock_config_entry.add_to_hass(hass)

    assert not mock_config_entry.options

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_DARK_MODE: False,
        CONF_LANGUAGE_OVERRIDE: "none",
        CONF_RADAR_STYLE: RadarStyle.OPTION_STYLE_STD,
    }

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_DARK_MODE: True,
            CONF_LANGUAGE_OVERRIDE: "fr",
            CONF_RADAR_STYLE: RadarStyle.OPTION_STYLE_YELLOW_RED,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_DARK_MODE: True,
        CONF_LANGUAGE_OVERRIDE: "fr",
        CONF_RADAR_STYLE: RadarStyle.OPTION_STYLE_YELLOW_RED,
    }

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
    } == {
        CONF_DARK_MODE: True,
        CONF_LANGUAGE_OVERRIDE: "fr",
        CONF_RADAR_STYLE: RadarStyle.OPTION_STYLE_YELLOW_RED,
    }


@pytest.mark.usefixtures("mock_setup_entry", "mock_config_flow_forecast")
async def test_reconfigure_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test moving the location within the same municipality."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 50.85, ATTR_LONGITUDE: 4.36}},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_LOCATION] == {
        ATTR_LATITUDE: 50.85,
        ATTR_LONGITUDE: 4.36,
    }


@pytest.mark.usefixtures("mock_setup_entry")
@pytest.mark.parametrize(
    ("title", "expected_title"),
    [
        pytest.param("Brussels", "Ghent", id="default_title"),
        pytest.param("Home", "Home", id="renamed_title"),
    ],
)
async def test_reconfigure_flow_other_municipality(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_flow_forecast: AsyncMock,
    title: str,
    expected_title: str,
) -> None:
    """Test moving the location to another municipality keeps the entities."""
    mock_config_flow_forecast.return_value = {"cityName": "Ghent", "country": "BE"}
    entry = MockConfigEntry(
        title=title,
        domain=DOMAIN,
        data={
            CONF_LOCATION: {ATTR_LATITUDE: 50.84, ATTR_LONGITUDE: 4.35},
            CONF_UNIQUE_ID: "brussels be",
        },
        unique_id="brussels be",
    )
    entry.add_to_hass(hass)
    weather = entity_registry.async_get_or_create(
        "weather", DOMAIN, "brussels be", config_entry=entry
    )
    sensor = entity_registry.async_get_or_create(
        "sensor", DOMAIN, "brussels be-temperature", config_entry=entry
    )

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 51.05, ATTR_LONGITUDE: 3.72}},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "ghent be"
    assert entry.title == expected_title
    assert entry.data == {
        CONF_LOCATION: {ATTR_LATITUDE: 51.05, ATTR_LONGITUDE: 3.72},
        CONF_UNIQUE_ID: "ghent be",
    }
    assert entity_registry.async_get(weather.entity_id).unique_id == "ghent be"
    assert (
        entity_registry.async_get(sensor.entity_id).unique_id == "ghent be-temperature"
    )


@pytest.mark.usefixtures("mock_setup_entry")
async def test_reconfigure_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_config_flow_forecast: AsyncMock,
) -> None:
    """Test moving the location to a municipality that is already configured."""
    mock_config_flow_forecast.return_value = {"cityName": "Ghent", "country": "BE"}
    mock_config_entry.add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, unique_id="ghent be").add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_LOCATION: {ATTR_LATITUDE: 51.05, ATTR_LONGITUDE: 3.72}},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.unique_id == "brussels be"
    assert mock_config_entry.data[CONF_LOCATION] == {
        ATTR_LATITUDE: 50.84,
        ATTR_LONGITUDE: 4.35,
    }


@pytest.mark.parametrize(
    ("selector", "options"),
    [
        pytest.param(
            CONF_LANGUAGE_OVERRIDE,
            CONF_LANGUAGE_OVERRIDE_OPTIONS,
            id="language_override",
        ),
        pytest.param(CONF_RADAR_STYLE, CONF_RADAR_STYLE_OPTIONS, id="radar_style"),
    ],
)
async def test_selector_options_are_translated(
    hass: HomeAssistant, selector: str, options: list[str]
) -> None:
    """Test every option of a selector has a translation."""
    translations = await async_get_translations(hass, "en", "selector", {DOMAIN})
    prefix = f"component.{DOMAIN}.selector.{selector}.options."

    assert {
        key.removeprefix(prefix) for key in translations if key.startswith(prefix)
    } == set(options)
