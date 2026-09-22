"""Health-workspace application for self-hosted and online deployments."""
import asyncio
import os
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from backend.app.http_application import create_http_app
from backend.app.api.router import health_router


@asynccontextmanager
async def health_lifespan(app):
    workers = [asyncio.create_task(app.state.services.notification_scheduler.run()),
               asyncio.create_task(app.state.services.memory_scheduler.run())]
    try:
        yield
    finally:
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker


def create_app(*, paths=None) -> FastAPI:
    app = create_http_app(paths=paths, lifespan=health_lifespan,
                          origins=("http://127.0.0.1:5173", "http://localhost:5174"))
    if not app.state.services.deployment.official:
        app.state.services.local_workspace.validate_storage()
    app.include_router(health_router(official=app.state.services.deployment.official))
    if frontend_root := os.environ.get("SERENITA_FRONTEND_ROOT"):
        from backend.app.web_frontend import mount_frontend
        mount_frontend(app, frontend_root)
    return app
