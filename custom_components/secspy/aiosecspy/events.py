"""Event stream parsing and watcher."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .const import (
    CLASSIFY_ABSENT,
    EVENT_RECONNECT_DELAY,
    EVENT_TIME_FORMAT,
    KNOWN_EVENT_TYPES,
    TRIGGER_REASON_NAMES,
    EventType,
    TriggerReason,
)

if TYPE_CHECKING:
    from .client import SecSpyClient

_LOGGER = logging.getLogger(__name__)

EventCallback = Callable[["Event"], Awaitable[None] | None]


@dataclass
class Event:
    """A parsed SecuritySpy event-stream line."""

    event_type: EventType
    event_id: int = -1
    camera_number: int | None = None
    when: datetime | None = None
    msg: str = ""
    raw: str = ""
    reasons: list[TriggerReason] = field(default_factory=list)
    reason_names: list[str] = field(default_factory=list)
    classify_human: int = CLASSIFY_ABSENT
    classify_vehicle: int = CLASSIFY_ABSENT
    classify_animal: int = CLASSIFY_ABSENT
    errors: list[str] = field(default_factory=list)


def parse_event_line(
    text: str,
    gmt_offset_hours: float = 0.0,
    *,
    major_version: int = 6,
) -> Event:
    """Parse one CR-delimited event stream line."""
    text = text.strip()
    parts = text.split(" ", 3)
    if len(parts) < 4:
        return Event(
            event_type=EventType.UNKNOWN,
            raw=text,
            msg=text,
            errors=["unknown_event"],
        )

    stamp, eid_s, cam_s, msg = parts[0], parts[1], parts[2], parts[3]
    event = Event(event_type=EventType.UNKNOWN, raw=text, msg=msg)

    try:
        # Local wall clock from SS; apply GMT offset hint when present.
        naive = datetime.strptime(stamp, EVENT_TIME_FORMAT)  # noqa: DTZ007
        # Keep as naive local-ish; consumers can treat as server local time.
        event.when = naive
        _ = gmt_offset_hours  # reserved for future tz-aware conversion
    except ValueError:
        event.when = datetime.now(UTC).replace(tzinfo=None)
        event.errors.append("date_parse_fail")

    try:
        event.event_id = int(eid_s)
    except ValueError:
        event.event_id = -2
        event.errors.append("id_parse_fail")

    cam_s = cam_s.removeprefix("CAM")
    if cam_s != "X":
        try:
            event.camera_number = int(cam_s)
        except ValueError:
            event.errors.append("cam_parse_fail")

    tokens = msg.split()
    type_s = tokens[0] if tokens else ""
    try:
        et = EventType(type_s)
    except ValueError:
        et = EventType.UNKNOWN
        event.errors.append("unknown_event")
    if et not in KNOWN_EVENT_TYPES and et not in {
        EventType.CONNECTED,
        EventType.DISCONNECTED,
        EventType.REFRESH,
        EventType.REFRESHFAIL,
        EventType.CUSTOM,
        EventType.ALL,
    }:
        if type_s in {e.value for e in KNOWN_EVENT_TYPES}:
            et = EventType(type_s)
        else:
            et = EventType.UNKNOWN
            if "unknown_event" not in event.errors:
                event.errors.append("unknown_event")
    event.event_type = et

    if et == EventType.CLASSIFY and len(tokens) > 1:
        _parse_classify(tokens[1:], event)

    if et in {EventType.TRIGGER_M, EventType.TRIGGER_A} and len(tokens) == 2:
        try:
            bitmask = int(tokens[1])
        except ValueError:
            bitmask = 0
        for flag in TriggerReason:
            if bitmask & int(flag) == 0:
                continue
            # v5 uses bit 512 for Animal; v6 uses 512 for HomeKit and 1024 for Animal.
            if (
                major_version < 6
                and flag == TriggerReason.HOMEKIT
                and bitmask & int(TriggerReason.ANIMAL) == 0
            ):
                event.reasons.append(TriggerReason.ANIMAL)
                event.reason_names.append(
                    TRIGGER_REASON_NAMES[TriggerReason.ANIMAL]
                )
                continue
            if major_version < 6 and flag == TriggerReason.ANIMAL:
                continue
            event.reasons.append(flag)
            event.reason_names.append(TRIGGER_REASON_NAMES.get(flag, flag.name))

    return event


def _parse_classify(parts: list[str], event: Event) -> None:
    for idx in range(0, len(parts) - 1, 2):
        label = parts[idx].upper()
        try:
            value = int(parts[idx + 1])
        except ValueError:
            continue
        if label == "HUMAN":
            event.classify_human = value
        elif label == "VEHICLE":
            event.classify_vehicle = value
        elif label == "ANIMAL":
            event.classify_animal = value


class EventStream:
    """Long-lived ++eventStream reader with reconnect."""

    def __init__(self, client: SecSpyClient) -> None:
        self._client = client
        self._callbacks: list[EventCallback] = []
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._refresh_on_config_change = True
        self.running = False

    def add_listener(self, callback: EventCallback) -> Callable[[], None]:
        """Register an async/sync callback; returns unsubscribe."""
        self._callbacks.append(callback)

        def _unsub() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return _unsub

    def start(
        self,
        *,
        reconnect_delay: float = EVENT_RECONNECT_DELAY,
        refresh_on_config_change: bool = True,
    ) -> None:
        """Start the background watcher task."""
        if self._task and not self._task.done():
            return
        self._refresh_on_config_change = refresh_on_config_change
        self._stop.clear()
        self.running = True
        self._task = asyncio.create_task(
            self._watch_loop(reconnect_delay), name="aiosecspy-eventstream"
        )

    async def stop(self) -> None:
        """Stop the watcher and wait for exit."""
        self._stop.set()
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _emit(self, event: Event) -> None:
        for cb in list(self._callbacks):
            try:
                result = cb(event)
                if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                    await result  # type: ignore[arg-type]
            except Exception:
                _LOGGER.exception("Event listener failed for %s", event.event_type)

    async def _watch_loop(self, reconnect_delay: float) -> None:
        from .exceptions import AuthenticationError

        while not self._stop.is_set():
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except AuthenticationError as err:
                _LOGGER.error("Event stream authentication failed: %s", err)
                await self._emit(
                    Event(
                        event_type=EventType.DISCONNECTED,
                        msg=str(err),
                        event_id=-10000,
                    )
                )
                self.running = False
                return
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Event stream error: %s", err)
                await self._emit(
                    Event(
                        event_type=EventType.DISCONNECTED,
                        msg=str(err),
                        event_id=-10000,
                    )
                )
            if self._stop.is_set():
                break
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=reconnect_delay)
            except TimeoutError:
                continue

    async def _run_once(self) -> None:
        assert self._client.session is not None
        url = self._client._url("++eventStream")
        params = self._client._params({"version": "3"})
        timeout = self._client._stream_timeout()

        async with self._client.session.get(
            url, params=params, timeout=timeout, ssl=self._client.verify_ssl
        ) as resp:
            if resp.status in {401, 403}:
                from .exceptions import AuthenticationError

                raise AuthenticationError(f"event stream auth failed: {resp.status}")
            resp.raise_for_status()
            await self._emit(
                Event(
                    event_type=EventType.CONNECTED,
                    msg="Event Stream Connected",
                    event_id=-9999,
                )
            )
            buffer = bytearray()
            async for chunk in resp.content.iter_any():
                if self._stop.is_set():
                    return
                buffer.extend(chunk)
                while True:
                    idx = buffer.find(b"\r")
                    if idx < 0:
                        break
                    line = bytes(buffer[:idx]).decode("utf-8", errors="replace")
                    del buffer[: idx + 1]
                    if line.count(" ") < 3:
                        continue
                    gmt_h = (
                        self._client.info.gmt_offset_seconds / 3600.0
                        if self._client.info
                        else 0.0
                    )
                    major = (
                        self._client.info.major_version if self._client.info else 6
                    )
                    event = parse_event_line(line, gmt_h, major_version=major)
                    if (
                        event.event_type == EventType.CONFIGCHANGE
                        and self._refresh_on_config_change
                    ):
                        try:
                            await self._client.refresh()
                            await self._emit(
                                Event(
                                    event_type=EventType.REFRESH,
                                    msg="SystemInfo Refresh Success",
                                    event_id=-9998,
                                )
                            )
                        except Exception as err:  # noqa: BLE001
                            await self._emit(
                                Event(
                                    event_type=EventType.REFRESHFAIL,
                                    msg=str(err),
                                    event_id=-9997,
                                )
                            )
                    await self._emit(event)
