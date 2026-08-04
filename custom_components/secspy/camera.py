"""Camera entities for SecuritySpy."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_web
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SecSpyBaseEntity, async_add_camera_entities

if TYPE_CHECKING:
    from aiohttp import ClientResponse

    from . import SecSpyConfigEntry
    from .coordinator import SecSpyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SecSpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cameras."""
    runtime = entry.runtime_data
    async_add_camera_entities(
        runtime.coordinator,
        async_add_entities,
        lambda number: [
            SecSpyCamera(runtime.coordinator, number, disable_rtsp=runtime.disable_rtsp)
        ],
    )


class SecSpyCamera(SecSpyBaseEntity, Camera):
    """SecuritySpy camera with snapshot and stream (proxied MJPEG or RTSP)."""

    _attr_name = None  # Use device name as entity name

    def __init__(
        self, coordinator: SecSpyCoordinator, camera_number: int, *, disable_rtsp: bool
    ) -> None:
        """Initialize both entity bases (they are not cooperative)."""
        # BaseCoordinatorEntity.__init__ is not cooperative (it never calls
        # super().__init__()), so the chain would never reach Camera.__init__;
        # both initializers must be invoked directly.
        Camera.__init__(self)
        SecSpyBaseEntity.__init__(self, coordinator, camera_number, key="camera")
        self._disable_rtsp = disable_rtsp
        # STREAM advertises an HLS-capable stream_source(); only true when the
        # user opted into RTSP. In MJPEG-proxy mode the frontend must use the
        # MJPEG endpoint, and advertising STREAM would break the picture.
        self._attr_supported_features = (
            CameraEntityFeature(0) if disable_rtsp else CameraEntityFeature.STREAM
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image."""
        return await self.coordinator.client.get_image(
            self.camera_number, width=width, height=height
        )

    async def stream_source(self) -> str | None:
        """Return the RTSP stream URL (credentials in userinfo).

        Only used when Disable RTSP is off; the user explicitly opts into
        handing the embedded credentials to their frontend/stream player.
        """
        if self._disable_rtsp:
            return None
        return self.coordinator.client.rtsp_url(self.camera_number)

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse:
        """Proxy the SecuritySpy ++video MJPEG stream through Home Assistant.

        Used when Disable RTSP is on: HA holds the credentials server-side and
        the frontend talks only to HA, so nothing secret lands in a URL.
        """
        if self._disable_rtsp:
            return await self._proxy_video(request)
        return await super().handle_async_mjpeg_stream(request)

    async def _proxy_video(self, request: web.Request) -> web.StreamResponse:
        url = self.coordinator.client.mjpeg_url(self.camera_number)
        verify_ssl = self.coordinator.client.verify_ssl
        # Returns a response object, or None if the client disconnected before
        # the upstream stream started; gateway errors raise HTTP errors here.
        response = await async_aiohttp_proxy_web(
            self.hass, request, self._video_request(url, verify_ssl=verify_ssl)
        )
        if response is None:
            # The viewer went away first; that is a normal close, not an error.
            return web.Response(status=HTTPStatus.NO_CONTENT)
        return response

    async def _video_request(self, url: str, *, verify_ssl: bool) -> ClientResponse:
        # Passed as an unawaited coroutine so HA can apply its own timeout and
        # 502/504 mapping while the connection is being established.
        client = self.coordinator.client
        session = client.session
        if session is None or session.closed:
            raise web.HTTPServiceUnavailable(text="SecuritySpy client is closed")
        return await session.get(url, ssl=verify_ssl)
