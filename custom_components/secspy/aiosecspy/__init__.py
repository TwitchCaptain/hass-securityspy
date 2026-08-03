"""Async SecuritySpy client library."""

from .client import SecSpyClient
from .const import CameraMode, EventType
from .events import Event, EventStream
from .exceptions import (
    AuthenticationError,
    SecSpyError,
    UnsupportedError,
)
from .models import Camera, PTZCapabilities, ServerInfo

__all__ = [
    "AuthenticationError",
    "Camera",
    "CameraMode",
    "Event",
    "EventStream",
    "EventType",
    "PTZCapabilities",
    "SecSpyClient",
    "SecSpyError",
    "ServerInfo",
    "UnsupportedError",
]

__version__ = "0.1.0"
