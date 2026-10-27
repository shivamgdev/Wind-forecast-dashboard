
from datetime import date, datetime, timezone

import httpx
import pytest

from app.elexon_client import ElexonAPIError, ElexonClient


@pytest.mark.asyncio
async def test_get_actuals_uses_wind_filter_and_date_range():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/FUELHH")
        assert request.url.params["fuelType"] == "WIND"
        assert request.url.params["settlementDateFrom"] == "2026-01-01"
        assert request.url.params["settlementDateTo"] == "2026-01-01"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "startTime": "2026-01-01T00:00:00Z",
                        "generation": 13756,
                    }
                ]
            },
        )

    client = ElexonClient(transport=httpx.MockTransport(handler))

    records = await client.get_actuals(date(2026, 1, 1), date(2026, 1, 1))

    assert len(records) == 1
    assert records[0]["generation"] == 13756


@pytest.mark.asyncio
async def test_get_forecasts_returns_valid_records():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/WINDFOR")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "startTime": "2026-01-01T00:00:00Z",
                        "publishTime": "2026-01-01T09:30:00Z",
                        "generation": 19960,
                    }
                ]
            },
        )

    client = ElexonClient(transport=httpx.MockTransport(handler))

    records = await client.get_forecasts(
        datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 9, 31, tzinfo=timezone.utc),
    )

    assert len(records) == 1
    assert records[0]["generation"] == 19960


@pytest.mark.asyncio
async def test_get_actuals_rejects_reversed_date_range():
    client = ElexonClient()

    with pytest.raises(ValueError, match="end_date"):
        await client.get_actuals(date(2026, 1, 2), date(2026, 1, 1))


@pytest.mark.asyncio
async def test_get_forecasts_rejects_timezone_naive_datetime():
    client = ElexonClient()

    with pytest.raises(ValueError, match="timezone"):
        await client.get_forecasts(
            datetime(2026, 1, 1, 9, 30),
            datetime(2026, 1, 1, 9, 31),
        )


@pytest.mark.asyncio
async def test_get_actuals_rejects_upstream_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = ElexonClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ElexonAPIError, match="HTTP 503") as exc_info:
        await client.get_actuals(date(2026, 1, 1), date(2026, 1, 1))

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_get_actuals_rejects_malformed_generation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "startTime": "2026-01-01T00:00:00Z",
                        "generation": None,
                    }
                ]
            },
        )

    client = ElexonClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ElexonAPIError, match="Invalid generation"):
        await client.get_actuals(date(2026, 1, 1), date(2026, 1, 1))


@pytest.mark.asyncio
async def test_repeated_identical_request_uses_cache():
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "startTime": "2026-01-01T00:00:00Z",
                        "generation": 13756,
                    }
                ]
            },
        )

    client = ElexonClient(transport=httpx.MockTransport(handler))

    first = await client.get_actuals(date(2026, 1, 1), date(2026, 1, 1))
    second = await client.get_actuals(date(2026, 1, 1), date(2026, 1, 1))

    assert request_count == 1
    assert first == second

    second[0]["generation"] = 1
    assert first[0]["generation"] == 13756


@pytest.mark.asyncio
async def test_different_actuals_date_ranges_use_separate_cache_entries():
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "startTime": "2026-01-01T00:00:00Z",
                        "generation": 13756,
                    }
                ]
            },
        )

    client = ElexonClient(transport=httpx.MockTransport(handler))

    await client.get_actuals(date(2026, 1, 1), date(2026, 1, 1))
    await client.get_actuals(date(2026, 1, 2), date(2026, 1, 2))

    assert request_count == 2
