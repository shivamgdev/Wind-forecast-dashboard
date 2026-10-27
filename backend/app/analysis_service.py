
import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from time import perf_counter
from typing import Any

from app.analysis import analyze_wind_forecasts
from app.elexon_client import ElexonClient


logger = logging.getLogger(__name__)


async def _get_actuals_in_chunks(
    start_date: date,
    end_date: date,
    client: ElexonClient,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    chunk_start = start_date

    while chunk_start <= end_date:
        chunk_end = min(
            chunk_start + timedelta(days=6),
            end_date,
        )
        records.extend(
            await client.get_actuals(chunk_start, chunk_end)
        )
        chunk_start = chunk_end + timedelta(days=1)

    return records


async def _get_forecasts_in_chunks(
    publish_from: datetime,
    publish_to: datetime,
    client: ElexonClient,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    chunk_start = publish_from

    while chunk_start <= publish_to:
        chunk_end = min(
            chunk_start + timedelta(days=6),
            publish_to,
        )
        records.extend(
            await client.get_forecasts(chunk_start, chunk_end)
        )
        chunk_start = chunk_end + timedelta(seconds=1)

    return records


async def build_analysis(
    start_date: date,
    end_date: date,
    decision_lead_hours: int,
    client: ElexonClient,
) -> dict[str, Any]:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    if (end_date - start_date).days > 30:
        raise ValueError("Date range cannot exceed 31 calendar days")

    if not 0 <= decision_lead_hours <= 168:
        raise ValueError("decision_lead_hours must be between 0 and 168")

    delivery_start = datetime.combine(
        start_date, time.min, tzinfo=timezone.utc
    )
    delivery_end = datetime.combine(
        end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
    )

    publish_from = delivery_start - timedelta(
        days=2, hours=decision_lead_hours
    )

    fetch_started_at = perf_counter()

    actuals, forecasts = await asyncio.gather(
        _get_actuals_in_chunks(start_date, end_date, client),
        _get_forecasts_in_chunks(publish_from, delivery_end, client),
    )

    logger.info(
        "Wind analysis source fetch completed: dates=%s..%s lead_hours=%d "
        "actual_records=%d forecast_records=%d elapsed_seconds=%.2f",
        start_date,
        end_date,
        decision_lead_hours,
        len(actuals),
        len(forecasts),
        perf_counter() - fetch_started_at,
    )

    analysis_started_at = perf_counter()

    result = analyze_wind_forecasts(
        actuals=actuals,
        forecasts=forecasts,
        decision_lead=timedelta(hours=decision_lead_hours),
        delivery_start=delivery_start,
        delivery_end=delivery_end,
    )

    logger.info(
        "Wind analysis calculation completed: elapsed_seconds=%.2f",
        perf_counter() - analysis_started_at,
    )

    return result
