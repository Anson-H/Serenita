"""Shared HTTP transport, error handling and request context."""
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.api.errors import error_http_status
from backend.app.application.services import ApplicationServices
from backend.app.core.business_operation import operation_scope, validate_operation_id
from backend.app.core.errors import SerenitaError
from backend.app.core.model_retry import configure_model_request_logging
from backend.app.storage.crypto import ProviderSecretError, WebSecretError
from backend.app.storage.sqlite import UnsupportedSchemaError


def create_http_app(*, paths=None, title="Serenita API", lifespan=None, origins=()) -> FastAPI:
    configure_model_request_logging()
    app = FastAPI(title=title, version="0.3.0", lifespan=lifespan)
    app.state.services = ApplicationServices(paths)

    @app.get("/api/deployment")
    def deployment():
        return {"mode": "official" if app.state.services.deployment.official else "self_hosted"}

    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

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
        operation_id = request.headers.get("X-Serenita-Operation-ID", str(uuid4()))
        try:
            validate_operation_id(operation_id)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"detail": {
                "code": "INVALID_OPERATION_ID", "message": str(exc),
            }}, headers={"Cache-Control": "private, no-store"})
        with operation_scope(operation_id, "manual"):
            response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["X-Serenita-Operation-ID"] = operation_id
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    from backend.app.api.models.errors import safe_model_error
    from backend.app.providers.errors import ProviderChatCompletionError, ProviderModelListError

    @app.exception_handler(ProviderChatCompletionError)
    @app.exception_handler(ProviderModelListError)
    async def model_service_error_handler(_request: Request, exc):
        return JSONResponse(status_code=502, content={"detail": safe_model_error(exc)})

    return app
