import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api import notifications, body_metrics, medications, medical_logs, account_settings, auth, conversations, favorites, members, model_providers, reports
from backend.app.core.errors import SerenitaError
from backend.app.api.errors import error_http_status
from backend.app.storage.crypto import ProviderSecretError, WebSecretError
from backend.app.storage.sqlite import UnsupportedSchemaError


def create_app(*, paths=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        worker = asyncio.create_task(app.state.services.notification_scheduler.run())
        try:
            yield
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
    app = FastAPI(title="Serenita API", version="0.2.0", lifespan=lifespan)
    from backend.app.application.services import ApplicationServices
    app.state.services = ApplicationServices(paths)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):517[0-9]$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, exc: RequestValidationError):
        errors = [{"loc": list(error["loc"]), "type": error["type"],
                   "message": error["msg"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": {
            "code": "REQUEST_VALIDATION_FAILED",
            "message": "；".join(error["message"] for error in errors),
            "details": errors,
        }})

    @app.exception_handler(SerenitaError)
    async def auth_service_error_handler(_request: Request, exc: SerenitaError):
        return JSONResponse(
            status_code=error_http_status(exc),
            content={"detail": exc.detail},
        )

    @app.exception_handler(ProviderSecretError)
    async def provider_secret_error_handler(_request: Request, exc: ProviderSecretError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "PROVIDER_SECRET_UNAVAILABLE",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(UnsupportedSchemaError)
    async def unsupported_schema_handler(_request: Request, exc: UnsupportedSchemaError):
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "UNSUPPORTED_SCHEMA",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(WebSecretError)
    async def web_secret_error_handler(_request: Request, exc: WebSecretError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "WEB_SECRET_UNAVAILABLE",
                    "message": str(exc),
                }
            },
        )

    @app.middleware("http")
    async def prevent_sensitive_api_caching(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    app.include_router(notifications.router)
    app.include_router(auth.router)
    app.include_router(account_settings.router)
    app.include_router(model_providers.router)
    app.include_router(conversations.router)
    app.include_router(favorites.router)
    app.include_router(reports.router)
    app.include_router(members.router)
    app.include_router(medical_logs.router)
    app.include_router(medications.router)
    app.include_router(body_metrics.router)
    return app
