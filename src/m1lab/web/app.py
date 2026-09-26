"""FastAPI application for the owner-facing interface."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
from dataclasses import asdict, dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from m1lab.core.errors import CoreError

from .facade import (
    OperatorCommand,
    OperatorFacade,
    Owner,
    UnavailableFacade,
    ViewName,
)


PACKAGE_DIR = Path(__file__).parent
VIEW_NAMES: tuple[ViewName, ...] = (
    "overview",
    "evidence",
    "approvals",
    "conversation",
)


def _current_owner(request: Request) -> Owner:
    owner = getattr(request.state, "owner", None)
    if not isinstance(owner, Owner):
        raise HTTPException(status_code=403, detail="Owner access required.")
    return owner


OwnerDependency = Annotated[Owner, Depends(_current_owner)]


@dataclass(frozen=True, slots=True)
class WebSettings:
    """Ingress settings, with a loopback-only development default."""

    trust_tailscale_headers: bool = False
    owner_login: str | None = None
    csrf_secret: str = ""
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""

    @classmethod
    def from_env(cls) -> "WebSettings":
        return cls(
            trust_tailscale_headers=os.getenv("M1LAB_TRUST_TAILSCALE_HEADERS") == "1",
            owner_login=os.getenv("M1LAB_OWNER_LOGIN") or None,
            csrf_secret=os.getenv("M1LAB_CSRF_SECRET", ""),
            vapid_public_key=os.getenv("M1LAB_VAPID_PUBLIC_KEY", ""),
            vapid_private_key=os.getenv("M1LAB_VAPID_PRIVATE_KEY", ""),
            vapid_subject=os.getenv("M1LAB_VAPID_SUBJECT", ""),
        )

    @property
    def tailscale_mode(self) -> bool:
        return self.trust_tailscale_headers and bool(self.owner_login)


class CommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,79}$")
    expected_revision: str = Field(min_length=1, max_length=256)
    target_id: str | None = Field(default=None, max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("command_id")
    @classmethod
    def command_id_is_uuid(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as exc:
            raise ValueError("command_id must be a UUID") from exc
        return value


class PushKeysBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str = Field(min_length=32, max_length=256)
    auth: str = Field(min_length=16, max_length=128)


class PushSubscriptionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1, max_length=2_048)
    keys: PushKeysBody


class OwnerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, settings: WebSettings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith("/static/") or request.url.path in {
            "/manifest.webmanifest",
            "/service-worker.js",
        }:
            return await call_next(request)

        owner = self._owner(request)
        if owner is None:
            return JSONResponse(
                {"detail": "Owner access required."},
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        request.state.owner = owner
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    def _owner(self, request: Request) -> Owner | None:
        if self.settings.tailscale_mode:
            login = request.headers.get("Tailscale-User-Login")
            if not login or not hmac.compare_digest(login, self.settings.owner_login or ""):
                return None
            return Owner(
                login=login,
                display_name=request.headers.get("Tailscale-User-Name", login),
                source="tailscale",
            )

        client_host = request.client.host if request.client else ""
        try:
            is_loopback = ip_address(client_host).is_loopback
        except ValueError:
            is_loopback = client_host in {"localhost", "testclient"}
        if not is_loopback:
            return None
        return Owner(login="local-dev", display_name="Local owner", source="local")


class BrowserSafetyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, secret: str) -> None:
        super().__init__(app)
        self.secret = secret.encode()

    def _sign(self, nonce: str) -> str:
        signature = hmac.digest(self.secret, nonce.encode(), "sha256").hex()
        return f"{nonce}.{signature}"

    def _valid(self, token: str) -> bool:
        nonce, separator, _ = token.partition(".")
        return bool(separator and nonce and hmac.compare_digest(token, self._sign(nonce)))

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        token = request.cookies.get("m1lab_csrf", "")
        if not self._valid(token):
            token = self._sign(secrets.token_urlsafe(24))

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            csrf = request.headers.get("X-CSRF-Token", "")
            if not origin or not self._same_origin(origin, request) or not hmac.compare_digest(csrf, token):
                return JSONResponse(
                    {"detail": "Current same-origin CSRF token required."},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )

        response = await call_next(request)
        response.set_cookie(
            "m1lab_csrf",
            token,
            secure=request.url.scheme == "https",
            httponly=False,
            samesite="strict",
            path="/",
        )
        return response

    @staticmethod
    def _same_origin(origin: str, request: Request) -> bool:
        parsed = urlsplit(origin)
        return parsed.scheme == request.url.scheme and parsed.netloc == request.headers.get("host")


def create_app(
    facade: OperatorFacade | None = None,
    settings: WebSettings | None = None,
) -> FastAPI:
    """Create the owner UI around a coordinator-provided facade."""

    facade = facade or UnavailableFacade()
    settings = settings or WebSettings.from_env()
    csrf_secret = settings.csrf_secret or secrets.token_urlsafe(32)

    app = FastAPI(
        title="M1 Power Lab",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.operator_facade = facade
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    app.add_middleware(BrowserSafetyMiddleware, secret=csrf_secret)
    app.add_middleware(OwnerAuthMiddleware, settings=settings)
    push_runner = getattr(facade, "run_push_notifications", None)
    if push_runner is not None and settings.vapid_public_key and settings.vapid_private_key and settings.vapid_subject:
        async def start_push_delivery() -> None:
            app.state.push_delivery_task = asyncio.create_task(push_runner())

        async def stop_push_delivery() -> None:
            task = getattr(app.state, "push_delivery_task", None)
            if task is None:
                return
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        app.router.add_event_handler("startup", start_push_delivery)
        app.router.add_event_handler("shutdown", stop_push_delivery)

    host_safety_runner = getattr(facade, "run_host_safety", None)
    if host_safety_runner is not None and getattr(facade, "investigator", None) is not None:
        async def start_host_safety() -> None:
            app.state.host_safety_task = asyncio.create_task(host_safety_runner())

        async def stop_host_safety() -> None:
            task = getattr(app.state, "host_safety_task", None)
            if task is None:
                return
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        app.router.add_event_handler("startup", start_host_safety)
        app.router.add_event_handler("shutdown", stop_host_safety)

    closer = getattr(facade, "close", None)
    if closer is not None:
        app.router.add_event_handler("shutdown", closer)

    templates = Environment(
        loader=FileSystemLoader(PACKAGE_DIR / "templates"),
        autoescape=select_autoescape(("html", "xml")),
        enable_async=False,
    )
    templates.filters["compact_number"] = _compact_number
    templates.filters["duration"] = _duration
    templates.filters["percent"] = _percent

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/overview", status_code=303)

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest() -> FileResponse:
        return FileResponse(
            PACKAGE_DIR / "static" / "manifest.webmanifest",
            media_type="application/manifest+json",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get("/service-worker.js", include_in_schema=False)
    async def service_worker() -> FileResponse:
        return FileResponse(
            PACKAGE_DIR / "static" / "service-worker.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/{view_name}", include_in_schema=False)
    async def view(request: Request, view_name: str, owner: OwnerDependency) -> Response:
        if view_name not in VIEW_NAMES:
            raise HTTPException(status_code=404, detail="View not found.")
        try:
            view_data = dict(await facade.get_view(view_name, owner))  # type: ignore[arg-type]
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        context = {
            "request": request,
            "active_view": view_name,
            "owner": owner,
            "data": view_data,
            "revision": str(view_data.get("revision", "unknown")),
            "tailscale_mode": settings.tailscale_mode,
        }
        template = templates.get_template(f"{view_name}.html")
        return Response(template.render(**context), media_type="text/html")

    @app.post("/api/commands")
    async def command(body: CommandBody, owner: OwnerDependency) -> JSONResponse:
        receipt = await facade.submit(
            OperatorCommand(
                command_id=body.command_id,
                kind=body.kind,
                expected_revision=body.expected_revision,
                target_id=body.target_id,
                payload=body.payload,
            ),
            owner,
        )
        status_code = 409 if receipt.status == "rejected" else 202
        return JSONResponse(asdict(receipt), status_code=status_code)

    @app.get("/api/push/config")
    async def push_config(owner: OwnerDependency) -> JSONResponse:
        status = getattr(facade, "push_status", None)
        if status is None:
            return JSONResponse({"enabled": False, "enrolled": False, "public_key": None})
        try:
            return JSONResponse(status(owner))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/push/subscription")
    async def push_subscribe(body: PushSubscriptionBody, owner: OwnerDependency) -> JSONResponse:
        subscribe = getattr(facade, "subscribe_push", None)
        if subscribe is None:
            raise HTTPException(status_code=501, detail="Push enrollment is unavailable.")
        try:
            subscribe(
                owner,
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"enrolled": True}, status_code=201)

    @app.delete("/api/push/subscription")
    async def push_unsubscribe(body: PushSubscriptionBody, owner: OwnerDependency) -> JSONResponse:
        unsubscribe = getattr(facade, "unsubscribe_push", None)
        if unsubscribe is None:
            raise HTTPException(status_code=501, detail="Push enrollment is unavailable.")
        try:
            changed = unsubscribe(owner, endpoint=body.endpoint)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return JSONResponse({"enrolled": False, "revoked": changed})

    @app.get("/api/events")
    async def events(request: Request, owner: OwnerDependency, cursor: str | None = None) -> StreamingResponse:
        try:
            await facade.get_view("overview", owner)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        after_cursor = request.headers.get("Last-Event-ID") or cursor

        async def encode_events():
            yield "retry: 2500\n\n"
            async for event in facade.stream_events(after_cursor, owner):
                data = json.dumps(
                    {
                        "kind": event.kind,
                        "revision": event.revision,
                        "payload": event.payload,
                    },
                    separators=(",", ":"),
                )
                yield f"id: {event.cursor}\ndata: {data}\n\n"

        return StreamingResponse(
            encode_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/export")
    async def export(owner: OwnerDependency) -> JSONResponse:
        try:
            await facade.get_view("overview", owner)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        exporter = getattr(facade, "export", None)
        if exporter is None:
            raise HTTPException(status_code=501, detail="Evidence export is unavailable.")
        return JSONResponse(
            exporter(),
            headers={"Content-Disposition": 'attachment; filename="m1-power-lab-export.json"'},
        )

    @app.get("/api/artifacts/{artifact_id}")
    async def artifact(artifact_id: str, owner: OwnerDependency) -> Response:
        try:
            await facade.get_view("overview", owner)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        reader = getattr(facade, "artifact", None)
        if reader is None:
            raise HTTPException(status_code=501, detail="Artifact inspection is unavailable.")
        try:
            content, media_type = reader(artifact_id)
        except (CoreError, ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact_id}"'},
        )

    @app.post("/api/jobs/{job_id}/interrupt")
    async def interrupt_job(job_id: str, owner: OwnerDependency) -> JSONResponse:
        interrupter = getattr(facade, "interrupt_job", None)
        if interrupter is None:
            raise HTTPException(status_code=501, detail="Job interruption is unavailable.")
        try:
            result = await interrupter(job_id, owner)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (CoreError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(result, status_code=202)

    return app


def _compact_number(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "—"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(number)


def _duration(value: Any) -> str:
    try:
        seconds = max(0, int(value))
    except (TypeError, ValueError):
        return "—"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _percent(value: Any, total: Any) -> str:
    try:
        return f"{min(100, max(0, float(value) / float(total) * 100)):.0f}"
    except (TypeError, ValueError, ZeroDivisionError):
        return "0"
