"""Camera platform stream behavior tests."""

from __future__ import annotations

from homeassistant.components.camera import CameraEntityFeature

from custom_components.secspy.camera import SecSpyCamera
from custom_components.secspy.coordinator import SecSpyCoordinator

from .conftest import make_camera, make_client


def _camera(hass, entry, *, disable_rtsp: bool) -> SecSpyCamera:
    client = make_client({1: make_camera(1)})
    coordinator = SecSpyCoordinator(hass, entry, client)
    coordinator.async_set_updated_data(dict(client.cameras))
    return SecSpyCamera(coordinator, 1, disable_rtsp=disable_rtsp)


async def test_mjpeg_proxy_mode_does_not_advertise_stream(hass, mock_config_entry):
    """With RTSP disabled there is no stream_source, so STREAM must be off."""
    cam = _camera(hass, mock_config_entry, disable_rtsp=True)
    assert cam.supported_features == CameraEntityFeature(0)
    assert await cam.stream_source() is None


async def test_rtsp_mode_advertises_stream_with_url(hass, mock_config_entry):
    cam = _camera(hass, mock_config_entry, disable_rtsp=False)
    assert cam.supported_features == CameraEntityFeature.STREAM
    source = await cam.stream_source()
    assert source is not None
    assert source.startswith("rtsp://")
    assert "cameraNum=1" in source


async def test_stream_sensor_tracks_coordinator(hass, mock_config_entry):
    from custom_components.secspy.binary_sensor import SecSpyStreamSensor

    client = make_client()
    coordinator = SecSpyCoordinator(hass, mock_config_entry, client)
    coordinator.async_set_updated_data(dict(client.cameras))
    sensor = SecSpyStreamSensor(coordinator)
    assert sensor.is_on is False
    coordinator._stream_connected = True
    assert sensor.is_on is True
