from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.session import engine
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.readiness import ReadinessChecker, ReadinessError

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


def get_readiness_checker() -> ReadinessChecker:
    return ReadinessChecker(engine)


@router.get("/ready", response_model=ReadinessResponse)
def readiness_check(
    checker: Annotated[ReadinessChecker, Depends(get_readiness_checker)],
) -> ReadinessResponse:
    try:
        result = checker.check()
    except ReadinessError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "database": exc.database,
                "migration": exc.migration,
            },
        ) from exc
    return ReadinessResponse(
        status="ready",
        database=result.database,
        migration=result.migration,
    )
