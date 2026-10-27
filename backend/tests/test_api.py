
from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.elexon_client import ElexonAPIError
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_analysis_defaults_to_january_2026():
    result = {
        "metrics": {
            "mae_mw": 100.0,
            "rmse_mw": 120.0,
            "bias_mw": -10.0,
        },
        "coverage": {
            "total_hours": 744,
            "matched_hours": 740,
            "missing_forecast_hours": 2,
            "missing_actual_hours": 4,
        },
        "intervals": [],
    }

    with patch("app.main.build_analysis", new_callable=AsyncMock) as mocked:
        mocked.return_value = result

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/analysis")

    assert response.status_code == 200
    assert response.json()["coverage"]["total_hours"] == 744
    mocked.assert_awaited_once()

    kwargs = mocked.await_args.kwargs
    assert kwargs["start_date"] == date(2026, 1, 1)
    assert kwargs["end_date"] == date(2026, 1, 31)
    assert kwargs["decision_lead_hours"] == 24


@pytest.mark.asyncio
async def test_analysis_rejects_reversed_dates():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/analysis",
            params={
                "start_date": "2026-01-31",
                "end_date": "2026-01-01",
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analysis_rejects_range_over_31_days():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/analysis",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-02-01",
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analysis_rejects_invalid_lead_time():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/analysis",
            params={"decision_lead_hours": 169},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analysis_returns_upstream_error():
    with patch(
        "app.main.build_analysis",
        new_callable=AsyncMock,
        side_effect=ElexonAPIError("Elexon request timed out", 504),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/analysis")

    assert response.status_code == 504
    assert response.json()["detail"] == "Elexon request timed out"
