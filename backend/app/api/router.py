"""Explicit HTTP route assembly for a health workspace."""
from fastapi import APIRouter

from backend.app.api.accounts.auth import router as auth_router
from backend.app.api.accounts.members import router as members_router
from backend.app.api.accounts.settings import router as settings_router
from backend.app.api.body_metrics import router as body_metrics_router
from backend.app.api.conversations import router as conversations_router
from backend.app.api.favorites import router as favorites_router
from backend.app.api.knowledge.files import router as knowledge_router
from backend.app.api.knowledge.lab_catalog import router as lab_catalog_router
from backend.app.api.medical_logs import router as medical_logs_router
from backend.app.api.medications import router as medications_router
from backend.app.api.memory import router as memory_router
from backend.app.api.models.connection import router as model_connection_router
from backend.app.api.models.providers import router as model_providers_router
from backend.app.api.notifications import router as notifications_router
from backend.app.api.reports.router import router as reports_router


def health_router(*, official: bool) -> APIRouter:
    router = APIRouter()
    if official:
        from server.backend.models.api import router as official_models_router

        router.include_router(official_models_router)
    for routes in (
        model_connection_router, notifications_router, memory_router,
        knowledge_router, lab_catalog_router, auth_router, settings_router,
        model_providers_router, conversations_router, favorites_router,
        reports_router, members_router, medical_logs_router, medications_router,
        body_metrics_router,
    ):
        router.include_router(routes)
    return router
