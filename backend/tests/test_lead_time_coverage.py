from datetime import date, datetime, timedelta, timezone

import pytest

from app.analysis import analyze_wind_forecasts
from app.analysis_service import build_analysis

PUBLISH_INTERVAL = timedelta(hours=3)
MAX_HORIZON = timedelta(hours=66)

DELIVERY_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
DELIVERY_END = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _actuals(start: datetime, end: datetime) -> list[dict]:
    records = []
    current = start
    while current < end:
        for offset in (timedelta(0), timedelta(minutes=30)):
            records.append(
                {
                    "startTime": (current + offset).isoformat(),
                    "generation": 1100,
                }
            )
        current += timedelta(hours=1)
    return records


def _windfor_feed(
    start: datetime,
    end: datetime,
    max_horizon: timedelta = MAX_HORIZON,
) -> list[dict]:
    records = []
    publish = start - max_horizon
    while publish < end:
        delivery = max(publish, start)
        while delivery < end and delivery - publish <= max_horizon:
            records.append(
                {
                    "startTime": delivery.isoformat(),
                    "publishTime": publish.isoformat(),
                    "generation": 1000,
                }
            )
            delivery += timedelta(hours=1)
        publish += PUBLISH_INTERVAL
    return records


def _run(forecasts: list[dict], lead_hours: int) -> dict:
    return analyze_wind_forecasts(
        actuals=_actuals(DELIVERY_START, DELIVERY_END),
        forecasts=forecasts,
        decision_lead=timedelta(hours=lead_hours),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
    )


def test_24h_lead_matches_every_hour():
    result = _run(_windfor_feed(DELIVERY_START, DELIVERY_END), 24)

    assert result["coverage"]["matched_hours"] == 24
    assert result["coverage"]["missing_forecast_hours"] == 0
    assert result["metrics"]["mae_mw"] == pytest.approx(100)
    assert result["metrics"]["bias_mw"] == pytest.approx(-100)


def test_48h_lead_with_partial_forecast_coverage_counts_missing_hours():
    forecasts = [
        record
        for record in _windfor_feed(DELIVERY_START, DELIVERY_END)
        if datetime.fromisoformat(record["startTime"]).hour % 2 == 0
    ]

    result = _run(forecasts, 48)

    assert result["coverage"]["matched_hours"] == 12
    assert result["coverage"]["missing_forecast_hours"] == 12
    assert result["coverage"]["missing_actual_hours"] == 0
    statuses = [interval["status"] for interval in result["intervals"]]
    assert statuses.count("missing_forecast") == 12
    assert result["metrics"]["mae_mw"] == pytest.approx(100)


ONE_HOUR_ACTUALS = [
    {"startTime": "2026-01-01T00:00:00Z", "generation": 1100},
    {"startTime": "2026-01-01T00:30:00Z", "generation": 1100},
]
ONE_HOUR_WINDOW = {
    "delivery_start": datetime(2026, 1, 1, 0, tzinfo=timezone.utc),
    "delivery_end": datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
}


def test_forecast_published_after_72h_cutoff_is_excluded():
    result = analyze_wind_forecasts(
        actuals=ONE_HOUR_ACTUALS,
        forecasts=[
            {
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2025-12-29T01:00:00Z",
                "generation": 1000,
            }
        ],
        decision_lead=timedelta(hours=72),
        **ONE_HOUR_WINDOW,
    )

    interval = result["intervals"][0]
    assert interval["status"] == "missing_forecast"
    assert interval["forecast_mw"] is None
    assert interval["publish_time"] is None
    assert result["coverage"]["matched_hours"] == 0
    assert result["metrics"]["mae_mw"] is None


def test_forecast_published_at_72h_cutoff_is_matched():
    result = analyze_wind_forecasts(
        actuals=ONE_HOUR_ACTUALS,
        forecasts=[
            {
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2025-12-28T23:00:00Z",
                "generation": 900,
            },
            {
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2025-12-29T00:00:00Z",
                "generation": 1000,
            },
        ],
        decision_lead=timedelta(hours=72),
        **ONE_HOUR_WINDOW,
    )

    interval = result["intervals"][0]
    assert interval["status"] == "matched"
    assert interval["publish_time"] == "2025-12-29T00:00:00+00:00"
    assert interval["forecast_mw"] == 1000
    assert interval["error_mw"] == pytest.approx(-100)
    assert result["coverage"]["matched_hours"] == 1
    assert result["metrics"]["mae_mw"] == pytest.approx(100)


def test_missing_forecast_feed_returns_null_metrics_not_an_error():
    result = _run([], 24)

    assert result["coverage"]["matched_hours"] == 0
    assert result["coverage"]["missing_forecast_hours"] == 24
    assert result["metrics"]["mae_mw"] is None
    assert result["metrics"]["rmse_mw"] is None
    assert result["metrics"]["bias_mw"] is None


class _FakeElexonClient:
    async def get_actuals(self, start_date: date, end_date: date):
        start = datetime.combine(start_date, datetime.min.time(), timezone.utc)
        end = datetime.combine(
            end_date + timedelta(days=1),
            datetime.min.time(),
            timezone.utc,
        )
        return _actuals(start, end)

    async def get_forecasts(self, publish_from: datetime, publish_to: datetime):
        feed = _windfor_feed(
            DELIVERY_START - MAX_HORIZON,
            DELIVERY_END + MAX_HORIZON,
        )
        return [
            record
            for record in feed
            if publish_from
            <= datetime.fromisoformat(record["publishTime"])
            <= publish_to
        ]


@pytest.mark.asyncio
async def test_build_analysis_72h_lead_with_66h_fixture_feed_reports_missing_forecasts():
    result = await build_analysis(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        decision_lead_hours=72,
        client=_FakeElexonClient(),
    )

    assert result["coverage"]["matched_hours"] == 0
    assert result["coverage"]["missing_forecast_hours"] == 24
    assert result["metrics"]["mae_mw"] is None


@pytest.mark.asyncio
async def test_build_analysis_24h_lead_matches_end_to_end():
    result = await build_analysis(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        decision_lead_hours=24,
        client=_FakeElexonClient(),
    )

    assert result["coverage"]["matched_hours"] == 24
    assert result["metrics"]["mae_mw"] == pytest.approx(100)
