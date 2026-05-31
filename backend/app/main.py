from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import account_settings, auth, conversations, favorites, model_providers, reports
from backend.app.model_capabilities import migrate_existing_account_model_capabilities


def create_app() -> FastAPI:
    migrate_existing_account_model_capabilities()
    app = FastAPI(title="Serenita API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):517[0-9]$",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(account_settings.router)
    app.include_router(model_providers.router)
    app.include_router(conversations.router)
    app.include_router(favorites.router)
    app.include_router(reports.router)
    return app
