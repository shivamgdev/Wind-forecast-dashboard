
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.analysis import AnalysisDataError
from app.analysis_service import build_analysis
from app.elexon_client import ElexonAPIError, ElexonClient


class HealthResponse(BaseModel):
    status: str


class MetricsResponse(BaseModel):
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None


class CoverageResponse(BaseModel):
    total_hours: int
    matched_hours: int
    missing_forecast_hours: int
    missing_actual_hours: int


class IntervalResponse(BaseModel):
    delivery_time: str
    publish_time: str | None
    forecast_mw: float | None
    actual_mw: float | None
    error_mw: float | None
    status: Literal["matched", "missing_forecast", "missing_actuals"]


class AnalysisResponse(BaseModel):
    metrics: MetricsResponse
    coverage: CoverageResponse
    intervals: list[IntervalResponse]


app = FastAPI(
    title="Wind Forecast Accuracy API",
    description="Evaluates UK national wind generation forecasts against actual generation.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get(
    "/api/v1/analysis",
    response_model=AnalysisResponse,
    tags=["Analysis"],
)
async def get_analysis(
    start_date: date = Query(default=date(2026, 1, 1)),
    end_date: date = Query(default=date(2026, 1, 31)),
    decision_lead_hours: int = Query(default=24, ge=0, le=168),
) -> AnalysisResponse:
    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="end_date must be on or after start_date",
        )

    if (end_date - start_date).days > 30:
        raise HTTPException(
            status_code=422,
            detail="Date range cannot exceed 31 calendar days",
        )

    try:
        result = await build_analysis(
            start_date=start_date,
            end_date=end_date,
            decision_lead_hours=decision_lead_hours,
            client=ElexonClient(),
        )
    except ElexonAPIError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc
    except AnalysisDataError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Invalid data received from Elexon: {exc}",
        ) from exc

    return AnalysisResponse.model_validate(result)
