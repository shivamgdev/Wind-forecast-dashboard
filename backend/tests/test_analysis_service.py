
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.analysis_service import (
    _get_actuals_in_chunks,
    _get_forecasts_in_chunks,
)


@pytest.mark.asyncio
async def test_actuals_are_fetched_in_chunks_of_at_most_seven_dates():
    client = AsyncMock()
    client.get_actuals.return_value = []

    await _get_actuals_in_chunks(
        date(2026, 1, 1),
        date(2026, 1, 31),
        client,
    )

    calls = [
        call.args
        for call in client.get_actuals.await_args_list
    ]

    assert calls == [
        (date(2026, 1, 1), date(2026, 1, 7)),
        (date(2026, 1, 8), date(2026, 1, 14)),
        (date(2026, 1, 15), date(2026, 1, 21)),
        (date(2026, 1, 22), date(2026, 1, 28)),
        (date(2026, 1, 29), date(2026, 1, 31)),
    ]


@pytest.mark.asyncio
async def test_actuals_single_day_range_uses_one_request():
    client = AsyncMock()
    client.get_actuals.return_value = []

    await _get_actuals_in_chunks(
        date(2026, 1, 15),
        date(2026, 1, 15),
        client,
    )

    client.get_actuals.assert_awaited_once_with(
        date(2026, 1, 15),
        date(2026, 1, 15),
    )


@pytest.mark.asyncio
async def test_forecasts_are_fetched_in_bounded_chunks():
    client = AsyncMock()
    client.get_forecasts.return_value = []

    start = datetime(2025, 12, 29, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, tzinfo=timezone.utc)

    await _get_forecasts_in_chunks(start, end, client)

    calls = [
        call.args
        for call in client.get_forecasts.await_args_list
    ]

    assert len(calls) == 6
    assert calls[0][0] == start
    assert calls[-1][1] == end

    for chunk_start, chunk_end in calls:
        assert chunk_end >= chunk_start
        assert chunk_end - chunk_start <= timedelta(days=7)

    for previous, current in zip(calls, calls[1:]):
        assert current[0] == previous[1] + timedelta(seconds=1)


@pytest.mark.asyncio
async def test_chunk_helpers_return_all_records():
    client = AsyncMock()
    client.get_actuals.side_effect = [
        [{"id": 1}],
        [{"id": 2}],
    ]

    records = await _get_actuals_in_chunks(
        date(2026, 1, 1),
        date(2026, 1, 8),
        client,
    )

    assert records == [{"id": 1}, {"id": 2}]
    assert client.get_actuals.await_count == 2

