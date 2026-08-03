"""Async HTTP client for SecuritySpy."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlsplit

import aiohttp

from .const import (
    DEFAULT_TIMEOUT,
    PTZ_DOWN,
    PTZ_HOME_CMD,
    PTZ_LEFT,
    PTZ_PRESET_BASE,
    PTZ_RIGHT,
    PTZ_STOP,
    PTZ_UP,
    PTZ_ZOOM_IN,
    PTZ_ZOOM_OUT,
    CameraMode,
)
from .events import EventStream
from .exceptions import AuthenticationError, RequestError, UnsupportedError
from .models import Camera, ServerInfo
from .systeminfo import parse_system_info


class SecSpyClient:
    """Async SecuritySpy web API client."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        use_ssl: bool = False,
        verify_ssl: bool = True,
        session: aiohttp.ClientSession | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        scheme = "https" if use_ssl else "http"
        self.base_url = f"{scheme}://{host}:{port}/"
        self._username = username
        self._password = password
        self._auth = base64.urlsafe_b64encode(
            f"{username}:{password}".encode()
        ).decode()
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._session = session
        self._owns_session = session is None
        self.info: ServerInfo | None = None
        self.events = EventStream(self)

    @property
    def session(self) -> aiohttp.ClientSession | None:
        """Active aiohttp session."""
        return self._session

    @property
    def cameras(self) -> dict[int, Camera]:
        """Camera map from last refresh."""
        if not self.info:
            return {}
        return self.info.cameras

    def _url(self, api: str) -> str:
        path = api if api.startswith("++") else f"++{api}"
        return urljoin(self.base_url, path)

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"auth": self._auth}
        if extra:
            params.update(extra)
        return params

    def _timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=self.timeout)

    def _stream_timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=None, sock_connect=self.timeout)

    async def open(self) -> None:
        """Create session if needed and refresh systemInfo."""
        if self._session is None:
            connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
            self._session = aiohttp.ClientSession(connector=connector)
            self._owns_session = True
        await self.refresh()

    async def close(self) -> None:
        """Stop event stream and close owned session."""
        await self.events.stop()
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> SecSpyClient:
        await self.open()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _request(
        self,
        api: str,
        params: dict[str, Any] | None = None,
        *,
        expect_ok: bool = False,
    ) -> bytes:
        if self._session is None:
            raise RequestError("client session is not open")
        url = self._url(api)
        try:
            async with self._session.get(
                url,
                params=self._params(params),
                timeout=self._timeout(),
                ssl=self.verify_ssl,
            ) as resp:
                return await self._read_response(api, resp, expect_ok=expect_ok)
        except (AuthenticationError, UnsupportedError, RequestError):
            raise
        except aiohttp.ClientError as err:
            raise RequestError(f"{api} transport error: {err}") from err

    async def _read_response(
        self,
        label: str,
        resp: aiohttp.ClientResponse,
        *,
        expect_ok: bool = False,
    ) -> bytes:
        body = await resp.read()
        if resp.status in {401, 403}:
            raise AuthenticationError(
                f"authentication failed for {label}: HTTP {resp.status}"
            )
        if resp.status == 404 and expect_ok:
            raise UnsupportedError(f"{label} returned 404")
        if resp.status >= 400:
            raise RequestError(f"{label} failed: HTTP {resp.status} {body[:200]!r}")
        if expect_ok:
            text = body.decode("utf-8", errors="replace").strip()
            compact = "".join(text.split())
            if not (text.endswith("OK") or '"result":"OK"' in compact):
                raise RequestError(f"{label} unexpected response: {text[:200]!r}")
        return body

    async def _request_text(
        self, api: str, params: dict[str, Any] | None = None
    ) -> str:
        return (await self._request(api, params)).decode("utf-8", errors="replace")

    async def _request_ok(
        self, api: str, params: dict[str, Any] | None = None
    ) -> None:
        await self._request(api, params, expect_ok=True)

    async def refresh(self) -> ServerInfo:
        """Fetch and parse ++systemInfo."""
        xml_text = await self._request_text("++systemInfo", {"format": "xml"})
        self.info = parse_system_info(xml_text)
        return self.info

    def camera(self, number: int) -> Camera:
        """Return camera by number or raise KeyError."""
        cams = self.cameras
        if number not in cams:
            raise KeyError(f"camera {number} not found")
        return cams[number]

    async def toggle_motion(self, camera_num: int, arm: bool) -> None:
        """Arm/disarm motion capture."""
        await self._request_ok(
            "++ssControlMotionCapture",
            {"cameraNum": camera_num, "arm": "1" if arm else "0"},
        )
        if camera_num in self.cameras:
            self.cameras[camera_num].mode_m = "armed" if arm else "disarmed"

    async def toggle_actions(self, camera_num: int, arm: bool) -> None:
        """Arm/disarm actions."""
        await self._request_ok(
            "++ssControlActions",
            {"cameraNum": camera_num, "arm": "1" if arm else "0"},
        )
        if camera_num in self.cameras:
            self.cameras[camera_num].mode_a = "armed" if arm else "disarmed"

    async def toggle_continuous(self, camera_num: int, arm: bool) -> None:
        """Arm/disarm continuous capture (may be unsupported)."""
        try:
            await self._request_ok(
                "++ssControlContinuous",
                {"cameraNum": camera_num, "arm": "1" if arm else "0"},
            )
        except (UnsupportedError, RequestError) as err:
            # Prefer schedule-based arming when soft toggle is missing.
            if self.info is None:
                raise UnsupportedError("continuous toggle unsupported") from err
            # Armed 24/7 is usually schedule id 1; Disarmed 24/7 is 0 — match by name.
            schedules = self.info.schedules
            if arm:
                sid = next(
                    (i for i, n in schedules.items() if "armed 24" in n.lower()),
                    1,
                )
            else:
                sid = next(
                    (i for i, n in schedules.items() if "disarmed 24" in n.lower()),
                    0,
                )
            await self.set_schedule(camera_num, CameraMode.CONTINUOUS, sid)
        if camera_num in self.cameras:
            self.cameras[camera_num].mode_c = "armed" if arm else "disarmed"

    async def trigger_motion(self, camera_num: int) -> None:
        """Manually trigger motion detection."""
        await self._request_ok("++triggermd", {"cameraNum": camera_num})

    async def set_schedule(
        self, camera_num: int, mode: CameraMode | str, schedule_id: int
    ) -> None:
        """Set camera schedule for mode C/M/A/X."""
        await self._request_ok(
            "++ssSetSchedule",
            {
                "cameraNum": camera_num,
                "mode": str(mode),
                "id": schedule_id,
            },
        )

    async def set_schedule_override(
        self, camera_num: int, mode: CameraMode | str, override_id: int
    ) -> None:
        """Set camera schedule override for mode C/M/A/X."""
        await self._request_ok(
            "++ssSetOverride",
            {
                "cameraNum": camera_num,
                "mode": str(mode),
                "id": override_id,
            },
        )

    async def set_schedule_preset(self, preset_id: int) -> None:
        """Activate a server-wide schedule preset."""
        await self._request_ok("++ssSetPreset", {"id": preset_id})

    async def camera_modes(self, camera_num: int) -> str:
        """Return raw ++cameramodes text."""
        return await self._request_text("++cameramodes", {"cameraNum": camera_num})

    async def get_image(
        self,
        camera_num: int,
        *,
        width: int | None = None,
        height: int | None = None,
        quality: int | None = None,
    ) -> bytes:
        """Download a JPEG snapshot."""
        params: dict[str, Any] = {"cameraNum": camera_num}
        if width is not None:
            params["width"] = width
        if height is not None:
            params["height"] = height
        if quality is not None:
            params["quality"] = quality
        return await self._request("++image", params)

    def image_url(
        self,
        camera_num: int,
        *,
        width: int | None = None,
        height: int | None = None,
        quality: int | None = 80,
    ) -> str:
        """Build an authenticated ++image URL."""
        params: dict[str, Any] = {"cameraNum": camera_num, "auth": self._auth}
        if width is not None:
            params["width"] = width
        if height is not None:
            params["height"] = height
        if quality is not None:
            params["quality"] = quality
        return f"{self._url('++image')}?{urlencode(params)}"

    def rtsp_url(self, camera_num: int, *, use_ssl: bool | None = None) -> str:
        """Build RTSP stream URL with userinfo auth.

        SecuritySpy RTSP expects credentials in the URL userinfo. Callers that
        must avoid embedding passwords should use mjpeg_url() / hls_url() with
        the auth query parameter instead.
        """
        ssl = self.base_url.startswith("https") if use_ssl is None else use_ssl
        scheme = "rtsps" if ssl else "rtsp"
        parts = urlsplit(self.base_url)
        host = parts.hostname or "127.0.0.1"
        if ":" in host:
            host = f"[{host}]"
        port = 8000
        if self.info:
            port = self.info.http_port or 8000
        elif parts.port:
            port = parts.port
        user = quote(self._username, safe="")
        password = quote(self._password, safe="")
        return (
            f"{scheme}://{user}:{password}@{host}:{port}"
            f"/stream?cameraNum={camera_num}"
        )

    def mjpeg_url(self, camera_num: int) -> str:
        """Build ++video MJPEG URL."""
        params = {"cameraNum": camera_num, "auth": self._auth}
        return f"{self._url('++video')}?{urlencode(params)}"

    def hls_url(self, camera_num: int) -> str:
        """Build ++hls URL (v6+)."""
        params = {"cameraNum": camera_num, "auth": self._auth}
        return f"{self._url('++hls')}?{urlencode(params)}"

    async def ptz_command(self, camera_num: int, command: int) -> None:
        """Send a PTZ command integer."""
        await self._request_ok(
            "++ptz/command",
            {"cameraNum": camera_num, "command": command},
        )

    async def ptz_left(self, camera_num: int) -> None:
        await self.ptz_command(camera_num, PTZ_LEFT)

    async def ptz_right(self, camera_num: int) -> None:
        await self.ptz_command(camera_num, PTZ_RIGHT)

    async def ptz_up(self, camera_num: int) -> None:
        await self.ptz_command(camera_num, PTZ_UP)

    async def ptz_down(self, camera_num: int) -> None:
        await self.ptz_command(camera_num, PTZ_DOWN)

    async def ptz_zoom(self, camera_num: int, zoom_in: bool = True) -> None:
        await self.ptz_command(camera_num, PTZ_ZOOM_IN if zoom_in else PTZ_ZOOM_OUT)

    async def ptz_home(self, camera_num: int) -> None:
        await self.ptz_command(camera_num, PTZ_HOME_CMD)

    async def ptz_stop(self, camera_num: int) -> None:
        await self.ptz_command(camera_num, PTZ_STOP)

    async def ptz_preset(self, camera_num: int, preset: int) -> None:
        """Move to preset 1-8."""
        if preset < 1 or preset > 8:
            raise ValueError("PTZ preset must be 1-8")
        await self.ptz_command(camera_num, PTZ_PRESET_BASE + (preset - 1))

    async def list_motion_files(
        self,
        camera_num: int | None = None,
        *,
        days: int = 1,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        """List recent motion capture files via ++download."""
        import xml.etree.ElementTree as ET

        params: dict[str, Any] = {
            "format": "xml",
            "ageText": str(days),
            "results": str(limit),
            "mcFilesCheck": "1",
        }
        if camera_num is not None:
            params["cameraNum"] = camera_num
        text = await self._request_text("++download", params)
        root = ET.fromstring(text)
        items = (
            root.findall(".//item")
            or root.findall(".//entry")
            or root.findall(".//file")
        )
        results: list[dict[str, str]] = []
        for item in items:
            title = item.findtext("title") or item.findtext("name") or ""
            link = item.find("link")
            href = ""
            if link is not None:
                href = link.attrib.get("href") or (link.text or "")
            if not href:
                href = item.findtext("href") or item.attrib.get("href") or ""
            if href:
                results.append({"title": title, "href": href})
        if not results:
            for el in root.iter():
                href = el.attrib.get("href") or ""
                if href and ("getfile" in href or href.startswith("++")):
                    title = el.findtext("title") or el.findtext("name") or el.tag
                    results.append({"title": title, "href": href})
        return results

    async def download_file(self, href: str) -> bytes:
        """Download a file by ++getfile* href."""
        path = href.lstrip("/")
        if not path.startswith("++"):
            # May be a full URL or query-only getfile link
            if "://" in path:
                if self._session is None:
                    raise RequestError("client session is not open")
                try:
                    async with self._session.get(
                        path,
                        params={"auth": self._auth},
                        timeout=self._timeout(),
                        ssl=self.verify_ssl,
                    ) as resp:
                        return await self._read_response(path, resp)
                except (AuthenticationError, UnsupportedError, RequestError):
                    raise
                except aiohttp.ClientError as err:
                    raise RequestError(f"{path} transport error: {err}") from err
            path = "++" + path
        # href may already include query string
        if "?" in path:
            api, _, query = path.partition("?")
            from urllib.parse import parse_qs

            q = {k: v[0] for k, v in parse_qs(query).items()}
            return await self._request(api, q)
        return await self._request(path)

    async def download_latest_motion_recording(self, camera_num: int) -> bytes:
        """Download the newest motion recording for a camera."""
        files = await self.list_motion_files(camera_num, days=7, limit=5)
        if not files:
            raise RequestError(f"no motion recordings found for camera {camera_num}")
        return await self.download_file(files[0]["href"])
