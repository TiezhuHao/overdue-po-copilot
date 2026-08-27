from fastapi import FastAPI

from app.api.health import readiness_check, router as health_router
from app.core.config import settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title=settings.app_name)
    app.include_router(health_router, prefix=settings.api_v1_prefix)
    app.add_api_route("/ready", readiness_check, methods=["GET"], include_in_schema=False)

    @app.get("/health", include_in_schema=False)
    def legacy_health_check() -> dict[str, str]:
        return {"status": "ok", "service": "overdue-po-copilot"}

    return app


app = create_app()
