
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
import math
from typing import Any


class AnalysisDataError(ValueError):
    pass


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise AnalysisDataError(f"{field} must be a timestamp string")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnalysisDataError(f"Invalid timestamp in {field}") from exc

    if parsed.tzinfo is None:
        raise AnalysisDataError(f"{field} must include a timezone")

    return parsed.astimezone(timezone.utc)


def _generation_value(record: dict[str, Any], index: int) -> float:
    value = record.get("generation")

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisDataError(f"Invalid generation at record {index}")

    result = float(value)

    if not math.isfinite(result) or result < 0:
        raise AnalysisDataError(f"Invalid generation at record {index}")

    return result


def analyze_wind_forecasts(
    actuals: list[dict[str, Any]],
    forecasts: list[dict[str, Any]],
    decision_lead: timedelta,
    delivery_start: datetime | None = None,
    delivery_end: datetime | None = None,
) -> dict[str, Any]:
    if decision_lead < timedelta(0):
        raise ValueError("decision_lead cannot be negative")

    if (delivery_start is None) != (delivery_end is None):
        raise ValueError("Both delivery_start and delivery_end are required")

    expected_hours: set[datetime] | None = None
    expected_actual_times: set[datetime] | None = None

    if delivery_start is not None and delivery_end is not None:
        delivery_start = _parse_timestamp(
            delivery_start.isoformat(), "delivery_start"
        )
        delivery_end = _parse_timestamp(
            delivery_end.isoformat(), "delivery_end"
        )

        if delivery_end <= delivery_start:
            raise ValueError("delivery_end must be after delivery_start")

        if any(
            value.minute or value.second or value.microsecond
            for value in (delivery_start, delivery_end)
        ):
            raise ValueError("Delivery boundaries must align to whole hours")

        expected_hours = set()
        current = delivery_start

        while current < delivery_end:
            expected_hours.add(current)
            current += timedelta(hours=1)

        expected_actual_times = expected_hours | {
            hour + timedelta(minutes=30) for hour in expected_hours
        }

    actual_by_time: dict[datetime, float] = {}

    for index, record in enumerate(actuals):
        start = _parse_timestamp(record.get("startTime"), "startTime")

        if start.minute not in (0, 30) or start.second or start.microsecond:
            raise AnalysisDataError(
                f"Actual timestamp is not aligned to a half-hour at record {index}"
            )

        if (
            expected_actual_times is not None
            and start not in expected_actual_times
        ):
            continue

        if start in actual_by_time:
            raise AnalysisDataError(
                f"Duplicate actual timestamp: {start.isoformat()}"
            )

        actual_by_time[start] = _generation_value(record, index)

    forecasts_by_delivery: dict[
        datetime, list[tuple[datetime, float]]
    ] = {}

    for index, record in enumerate(forecasts):
        delivery = _parse_timestamp(record.get("startTime"), "startTime")
        published = _parse_timestamp(record.get("publishTime"), "publishTime")

        if delivery.minute or delivery.second or delivery.microsecond:
            raise AnalysisDataError(
                f"Forecast timestamp is not hourly at record {index}"
            )

        if expected_hours is not None and delivery not in expected_hours:
            continue

        generation = _generation_value(record, index)

        forecasts_by_delivery.setdefault(delivery, []).append(
            (published, generation)
        )

    for delivery_forecasts in forecasts_by_delivery.values():
        delivery_forecasts.sort()

    delivery_times = (
        sorted(expected_hours)
        if expected_hours is not None
        else sorted(forecasts_by_delivery)
    )

    intervals: list[dict[str, Any]] = []
    errors: list[float] = []
    missing_forecast_hours = 0
    missing_actual_hours = 0

    for delivery in delivery_times:
        cutoff = delivery - decision_lead
        candidates = forecasts_by_delivery.get(delivery, [])

        eligible_end = bisect_right(candidates, (cutoff, math.inf))

        if eligible_end:
            latest_publish = candidates[eligible_end - 1][0]
            latest_start = bisect_left(
                candidates, (latest_publish, -math.inf)
            )

            if eligible_end - latest_start != 1:
                raise AnalysisDataError(
                    f"Ambiguous forecasts for {delivery.isoformat()}"
                )

            publish_time, forecast_mw = candidates[eligible_end - 1]
        else:
            forecast_mw = None
            publish_time = None
            missing_forecast_hours += 1

        first_actual = actual_by_time.get(delivery)
        second_actual = actual_by_time.get(
            delivery + timedelta(minutes=30)
        )

        if first_actual is not None and second_actual is not None:
            actual_mw = (first_actual + second_actual) / 2
        else:
            actual_mw = None

        if actual_mw is None:
            missing_actual_hours += 1

        if forecast_mw is None:
            status = "missing_forecast"
            error_mw = None
        elif actual_mw is None:
            status = "missing_actuals"
            error_mw = None
        else:
            status = "matched"
            error_mw = forecast_mw - actual_mw
            errors.append(error_mw)

        intervals.append(
            {
                "delivery_time": delivery.isoformat(),
                "publish_time": (
                    publish_time.isoformat() if publish_time else None
                ),
                "forecast_mw": forecast_mw,
                "actual_mw": actual_mw,
                "error_mw": error_mw,
                "status": status,
            }
        )

    matched_count = len(errors)
    total_count = len(intervals)

    metrics = {
        "mae_mw": (
            sum(abs(error) for error in errors) / matched_count
            if matched_count else None
        ),
        "rmse_mw": (
            math.sqrt(sum(error**2 for error in errors) / matched_count)
            if matched_count else None
        ),
        "bias_mw": (
            sum(errors) / matched_count
            if matched_count else None
        ),
    }

    return {
        "metrics": metrics,
        "coverage": {
            "total_hours": total_count,
            "matched_hours": matched_count,
            "missing_forecast_hours": missing_forecast_hours,
            "missing_actual_hours": missing_actual_hours,
        },
        "intervals": intervals,
    }
