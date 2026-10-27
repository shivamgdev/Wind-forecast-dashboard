
from datetime import datetime, timedelta, timezone
import math

import pytest

from app.analysis import AnalysisDataError, analyze_wind_forecasts


def actual(timestamp: str, generation: float) -> dict:
    return {"startTime": timestamp, "generation": generation}


def forecast(
    delivery: str,
    published: str,
    generation: float,
) -> dict:
    return {
        "startTime": delivery,
        "publishTime": published,
        "generation": generation,
    }


def test_matches_hourly_forecast_to_average_of_two_actuals():
    result = analyze_wind_forecasts(
        [
            actual("2026-01-01T10:00:00Z", 100),
            actual("2026-01-01T10:30:00Z", 120),
        ],
        [forecast("2026-01-01T10:00:00Z", "2026-01-01T09:00:00Z", 130)],
        timedelta(hours=1),
    )

    interval = result["intervals"][0]

    assert interval["actual_mw"] == 110
    assert interval["forecast_mw"] == 130
    assert interval["error_mw"] == 20
    assert interval["status"] == "matched"


def test_selects_latest_forecast_published_before_cutoff():
    result = analyze_wind_forecasts(
        [
            actual("2026-01-01T10:00:00Z", 100),
            actual("2026-01-01T10:30:00Z", 100),
        ],
        [
            forecast("2026-01-01T10:00:00Z", "2026-01-01T08:00:00Z", 120),
            forecast("2026-01-01T10:00:00Z", "2026-01-01T08:30:00Z", 140),
            forecast("2026-01-01T10:00:00Z", "2026-01-01T09:30:00Z", 180),
        ],
        timedelta(hours=1),
    )

    assert result["intervals"][0]["forecast_mw"] == 140
    assert result["intervals"][0]["publish_time"] == "2026-01-01T08:30:00+00:00"


def test_excludes_forecast_published_after_cutoff():
    result = analyze_wind_forecasts(
        [],
        [forecast("2026-01-01T10:00:00Z", "2026-01-01T09:30:00Z", 180)],
        timedelta(hours=1),
    )

    assert result["intervals"][0]["status"] == "missing_forecast"
    assert result["metrics"]["mae_mw"] is None
    assert result["coverage"]["missing_forecast_hours"] == 1


def test_incomplete_actual_pair_is_not_zero_filled():
    result = analyze_wind_forecasts(
        [actual("2026-01-01T10:00:00Z", 100)],
        [forecast("2026-01-01T10:00:00Z", "2026-01-01T09:00:00Z", 120)],
        timedelta(hours=1),
    )

    assert result["intervals"][0]["actual_mw"] is None
    assert result["intervals"][0]["error_mw"] is None
    assert result["intervals"][0]["status"] == "missing_actuals"
    assert result["coverage"]["missing_actual_hours"] == 1


def test_calculates_mae_rmse_and_bias():
    result = analyze_wind_forecasts(
        [
            actual("2026-01-01T10:00:00Z", 100),
            actual("2026-01-01T10:30:00Z", 120),
            actual("2026-01-01T11:00:00Z", 120),
            actual("2026-01-01T11:30:00Z", 140),
        ],
        [
            forecast("2026-01-01T10:00:00Z", "2026-01-01T09:00:00Z", 130),
            forecast("2026-01-01T11:00:00Z", "2026-01-01T10:00:00Z", 100),
        ],
        timedelta(hours=1),
    )

    assert result["metrics"]["mae_mw"] == 25
    assert math.isclose(result["metrics"]["rmse_mw"], math.sqrt(650))
    assert result["metrics"]["bias_mw"] == -5
    assert result["coverage"]["matched_hours"] == 2


def test_rejects_duplicate_actual_timestamps():
    with pytest.raises(AnalysisDataError, match="Duplicate actual"):
        analyze_wind_forecasts(
            [
                actual("2026-01-01T10:00:00Z", 100),
                actual("2026-01-01T10:00:00Z", 110),
            ],
            [],
            timedelta(hours=1),
        )


def test_rejects_negative_generation():
    with pytest.raises(AnalysisDataError, match="Invalid generation"):
        analyze_wind_forecasts(
            [],
            [forecast("2026-01-01T10:00:00Z", "2026-01-01T09:00:00Z", -1)],
            timedelta(hours=1),
        )


def test_rejects_negative_decision_lead():
    with pytest.raises(ValueError, match="decision_lead"):
        analyze_wind_forecasts([], [], timedelta(hours=-1))


def test_empty_input_returns_null_metrics():
    result = analyze_wind_forecasts([], [], timedelta(hours=1))

    assert result["intervals"] == []
    assert result["coverage"]["total_hours"] == 0
    assert result["metrics"] == {
        "mae_mw": None,
        "rmse_mw": None,
        "bias_mw": None,
    }
