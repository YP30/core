"""Tests for the IRM KMI image platform."""

import asyncio
from collections.abc import Generator
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from irm_kmi_api import IrmKmiApiError, RadarAnimationData, RadarStyle
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.homeassistant import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    SERVICE_UPDATE_ENTITY,
)
from homeassistant.components.image import async_get_image
from homeassistant.components.irm_kmi.const import CONF_DARK_MODE, CONF_RADAR_STYLE
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from . import setup_integration
from .const import ANIMATION, RADAR_ENTITY_ID

from tests.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_fixture,
    snapshot_platform,
)

RADAR_SVG = load_fixture("radar.svg", "irm_kmi").encode()
OTHER_RADAR_SVG = RADAR_SVG.replace(b"#385E95", b"#393C40")


@pytest.fixture(autouse=True)
def override_platforms() -> Generator[None]:
    """Load only the image platform."""
    with patch("homeassistant.components.irm_kmi.PLATFORMS", [Platform.IMAGE]):
        yield


@pytest.fixture(autouse=True)
def mock_getrandbits() -> Generator[None]:
    """Mock image access token which normally is randomized."""
    with patch(
        "homeassistant.components.image.SystemRandom.getrandbits",
        return_value=1,
    ):
        yield


@pytest.fixture
def mock_rain_graph() -> Generator[MagicMock]:
    """Mock the radar renderer."""
    with patch(
        "homeassistant.components.irm_kmi.image.RainGraph", autospec=True
    ) as rain_graph:
        graph = rain_graph.return_value
        graph.build.return_value = graph
        graph.get_animated.return_value = RADAR_SVG
        yield rain_graph


async def next_refresh(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Let the coordinator poll the API once more."""
    freezer.tick(timedelta(minutes=7))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
@pytest.mark.usefixtures("mock_irm_kmi_api", "mock_rain_graph")
async def test_radar_image(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the radar image entity and the bytes it serves."""
    await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)

    image = await async_get_image(hass, RADAR_ENTITY_ID)
    assert image.content_type == "image/svg+xml"
    assert image.content == RADAR_SVG


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
@pytest.mark.usefixtures("mock_rain_graph")
async def test_radar_without_animation_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_irm_kmi_api: MagicMock,
) -> None:
    """Test the entity is unavailable when the payload carries no radar loop."""
    mock_irm_kmi_api.get_animation_data.side_effect = ValueError

    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(RADAR_ENTITY_ID)
    assert state
    assert state.state == STATE_UNAVAILABLE

    with pytest.raises(HomeAssistantError):
        await async_get_image(hass, RADAR_ENTITY_ID)


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
@pytest.mark.usefixtures("mock_rain_graph")
async def test_radar_last_updated_follows_the_radar_loop(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_irm_kmi_api: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the image is only invalidated when the radar loop changes."""
    await setup_integration(hass, mock_config_entry)

    first = hass.states.get(RADAR_ENTITY_ID).state
    assert first == "2023-12-28T14:30:00+00:00"

    await next_refresh(hass, freezer)

    assert hass.states.get(RADAR_ENTITY_ID).state == first

    mock_irm_kmi_api.get_animation_data.return_value = RadarAnimationData(
        **{**ANIMATION, "hint": "Rain expected soon"}
    )

    await next_refresh(hass, freezer)

    state = hass.states.get(RADAR_ENTITY_ID)
    assert state.state == "2023-12-28T14:44:00+00:00"
    assert state.attributes["hint"] == "Rain expected soon"


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
async def test_radar_style_option_round_trip(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_irm_kmi_api: MagicMock,
    mock_rain_graph: MagicMock,
) -> None:
    """Test the radar options reach both the frame URLs and the rendering."""
    await setup_integration(hass, mock_config_entry)

    assert mock_irm_kmi_api.get_animation_data.call_args.args[2:] == (
        RadarStyle.OPTION_STYLE_STD,
        False,
    )
    mock_rain_graph.assert_not_called()

    image = await async_get_image(hass, RADAR_ENTITY_ID)
    assert image.content == RADAR_SVG
    assert mock_rain_graph.call_args.kwargs["style"] == RadarStyle.OPTION_STYLE_STD
    assert mock_rain_graph.call_args.kwargs["dark_mode"] is False

    mock_rain_graph.return_value.get_animated.return_value = OTHER_RADAR_SVG

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_RADAR_STYLE: RadarStyle.OPTION_STYLE_SATELLITE,
            CONF_DARK_MODE: True,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert mock_irm_kmi_api.get_animation_data.call_args.args[2:] == (
        RadarStyle.OPTION_STYLE_SATELLITE,
        True,
    )

    image = await async_get_image(hass, RADAR_ENTITY_ID)
    assert image.content == OTHER_RADAR_SVG
    assert (
        mock_rain_graph.call_args.kwargs["style"] == RadarStyle.OPTION_STYLE_SATELLITE
    )
    assert mock_rain_graph.call_args.kwargs["dark_mode"] is True


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
@pytest.mark.usefixtures("mock_get_forecasts_coord", "mock_get_image")
async def test_radar_serves_an_animated_svg(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the entity renders the frames of a recorded payload."""
    await setup_integration(hass, mock_config_entry)

    image = await async_get_image(hass, RADAR_ENTITY_ID)

    assert image.content_type == "image/svg+xml"
    assert image.content.startswith(b"<svg")
    assert b"<animate " in image.content


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
async def test_radar_downloads_the_frames_once_per_radar_loop(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_forecasts_coord: AsyncMock,
    mock_get_image: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the frames are downloaded once per radar loop."""
    await setup_integration(hass, mock_config_entry)

    assert mock_get_image.call_count == 0

    await async_get_image(hass, RADAR_ENTITY_ID)
    downloads = mock_get_image.call_count
    assert downloads == 12

    await async_get_image(hass, RADAR_ENTITY_ID)
    assert mock_get_image.call_count == downloads

    await next_refresh(hass, freezer)

    await async_get_image(hass, RADAR_ENTITY_ID)
    assert mock_get_image.call_count == downloads

    payload = deepcopy(mock_get_forecasts_coord.return_value)
    payload["animation"]["sequence"][0]["time"] = "2023-12-26T16:50:00+01:00"
    mock_get_forecasts_coord.return_value = payload

    await next_refresh(hass, freezer)

    await async_get_image(hass, RADAR_ENTITY_ID)
    assert mock_get_image.call_count == 2 * downloads


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
@pytest.mark.usefixtures("mock_get_forecasts_coord")
async def test_radar_concurrent_views_share_one_download(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_image: AsyncMock,
) -> None:
    """Test two views at the same time download the frames once."""
    await setup_integration(hass, mock_config_entry)

    first, second = await asyncio.gather(
        async_get_image(hass, RADAR_ENTITY_ID),
        async_get_image(hass, RADAR_ENTITY_ID),
    )

    assert first.content == second.content
    assert mock_get_image.call_count == 12


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
@pytest.mark.usefixtures("mock_get_forecasts_coord")
async def test_radar_recovers_from_a_download_that_times_out(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_image: AsyncMock,
) -> None:
    """Test a view that times out does not block the next one."""
    await setup_integration(hass, mock_config_entry)

    release = asyncio.Event()
    downloaded = mock_get_image.return_value

    async def _blocked_download(*args: object, **kwargs: object) -> bytes:
        await release.wait()
        return downloaded

    mock_get_image.side_effect = _blocked_download

    with pytest.raises(HomeAssistantError, match="Unable to get image"):
        await async_get_image(hass, RADAR_ENTITY_ID, timeout=0)

    release.set()

    image = await async_get_image(hass, RADAR_ENTITY_ID)
    assert image.content.startswith(b"<svg")


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
@pytest.mark.usefixtures("mock_get_forecasts_coord")
async def test_radar_when_the_frames_cannot_be_downloaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_image: AsyncMock,
) -> None:
    """Test a frame download failure raises a translated error."""
    mock_get_image.side_effect = IrmKmiApiError

    await setup_integration(hass, mock_config_entry)

    with pytest.raises(
        HomeAssistantError, match="The rain radar image could not be downloaded"
    ):
        await async_get_image(hass, RADAR_ENTITY_ID)

    mock_get_image.side_effect = None

    image = await async_get_image(hass, RADAR_ENTITY_ID)
    assert image.content.startswith(b"<svg")


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
async def test_radar_does_not_cache_a_render_outdated_by_a_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_forecasts_coord: AsyncMock,
    mock_get_image: AsyncMock,
) -> None:
    """Test a render that finishes after a new radar loop arrived is not kept."""
    await async_setup_component(hass, HOMEASSISTANT_DOMAIN, {})
    await setup_integration(hass, mock_config_entry)

    started = asyncio.Event()
    release = asyncio.Event()
    downloaded = mock_get_image.return_value

    async def _blocked_download(*args: object, **kwargs: object) -> bytes:
        started.set()
        await release.wait()
        return downloaded

    mock_get_image.side_effect = _blocked_download
    view = hass.async_create_task(async_get_image(hass, RADAR_ENTITY_ID))
    await started.wait()

    forecast = deepcopy(mock_get_forecasts_coord.return_value)
    forecast["animation"]["sequenceHint"]["en"] = "Rain expected soon"
    mock_get_forecasts_coord.return_value = forecast
    await hass.services.async_call(
        HOMEASSISTANT_DOMAIN,
        SERVICE_UPDATE_ENTITY,
        {ATTR_ENTITY_ID: RADAR_ENTITY_ID},
        blocking=True,
    )

    release.set()
    await view
    downloads = mock_get_image.call_count

    await async_get_image(hass, RADAR_ENTITY_ID)
    assert mock_get_image.call_count == 2 * downloads


@pytest.mark.freeze_time("2023-12-28T15:30:00+01:00")
@pytest.mark.usefixtures("mock_get_forecasts_coord")
async def test_radar_does_not_cache_a_render_without_rain(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_image: AsyncMock,
) -> None:
    """Test a render whose frames failed to download is redrawn on the next view."""
    downloaded = mock_get_image.return_value

    async def _frames_fail(url: str) -> bytes:
        if "getIncaImage" in url:
            raise IrmKmiApiError
        return downloaded

    mock_get_image.side_effect = _frames_fail
    await setup_integration(hass, mock_config_entry)

    image = await async_get_image(hass, RADAR_ENTITY_ID)
    assert image.content.startswith(b"<svg")
    failed = mock_get_image.call_count

    mock_get_image.side_effect = None
    await async_get_image(hass, RADAR_ENTITY_ID)
    await async_get_image(hass, RADAR_ENTITY_ID)

    assert mock_get_image.call_count == 2 * failed
