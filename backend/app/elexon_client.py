
import logging
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime
from time import monotonic, perf_counter
from typing import Any

import httpx


logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300.0
CACHE_MAX_ENTRIES = 128

CacheKey = tuple[str, str, tuple[tuple[str, str], ...], int]
CacheEntry = tuple[float, list[dict[str, Any]]]

_RESPONSE_CACHE: OrderedDict[CacheKey, CacheEntry] = OrderedDict()


class ElexonAPIError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class ElexonClient:
    def __init__(
        self,
        base_url: str = "https://data.elexon.co.uk/bmrs/api/v1/datasets",
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport

    async def get_actuals(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        return await self._get_records(
            "FUELHH",
            {
                "settlementDateFrom": start_date.isoformat(),
                "settlementDateTo": end_date.isoformat(),
                "fuelType": "WIND",
            },
            ("startTime", "generation"),
        )

    async def get_forecasts(
        self,
        publish_from: datetime,
        publish_to: datetime,
    ) -> list[dict[str, Any]]:
        if publish_from.tzinfo is None or publish_to.tzinfo is None:
            raise ValueError("Publication timestamps must include a timezone")

        if publish_to < publish_from:
            raise ValueError("publish_to must be on or after publish_from")

        return await self._get_records(
            "WINDFOR",
            {
                "publishDateTimeFrom": publish_from.isoformat(),
                "publishDateTimeTo": publish_to.isoformat(),
            },
            ("startTime", "publishTime", "generation"),
        )

    def _cache_key(
        self,
        dataset: str,
        params: dict[str, str],
    ) -> CacheKey:
        return (
            self._base_url,
            dataset,
            tuple(sorted(params.items())),
            id(self._transport) if self._transport is not None else 0,
        )

    def _get_cached_records(
        self,
        key: CacheKey,
    ) -> list[dict[str, Any]] | None:
        entry = _RESPONSE_CACHE.get(key)

        if entry is None:
            return None

        expires_at, records = entry

        if monotonic() >= expires_at:
            del _RESPONSE_CACHE[key]
            return None

        _RESPONSE_CACHE.move_to_end(key)
        return deepcopy(records)

    def _cache_records(
        self,
        key: CacheKey,
        records: list[dict[str, Any]],
    ) -> None:
        _RESPONSE_CACHE[key] = (
            monotonic() + CACHE_TTL_SECONDS,
            deepcopy(records),
        )
        _RESPONSE_CACHE.move_to_end(key)

        while len(_RESPONSE_CACHE) > CACHE_MAX_ENTRIES:
            _RESPONSE_CACHE.popitem(last=False)

    async def _get_records(
        self,
        dataset: str,
        params: dict[str, str],
        required_fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        started_at = perf_counter()
        cache_key = self._cache_key(dataset, params)
        cached_records = self._get_cached_records(cache_key)

        if cached_records is not None:
            logger.info(
                "Elexon cache hit: dataset=%s records=%d elapsed_seconds=%.2f",
                dataset,
                len(cached_records),
                perf_counter() - started_at,
            )
            return cached_records

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"{self._base_url}/{dataset}",
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            logger.warning(
                "Elexon request timed out: dataset=%s elapsed_seconds=%.2f",
                dataset,
                perf_counter() - started_at,
            )
            raise ElexonAPIError("Elexon request timed out", 504) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Elexon request returned HTTP %d: dataset=%s elapsed_seconds=%.2f",
                exc.response.status_code,
                dataset,
                perf_counter() - started_at,
            )
            raise ElexonAPIError(
                f"Elexon returned HTTP {exc.response.status_code}",
                502,
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Elexon connection failed: dataset=%s elapsed_seconds=%.2f",
                dataset,
                perf_counter() - started_at,
            )
            raise ElexonAPIError("Unable to connect to Elexon", 502) from exc
        except ValueError as exc:
            logger.warning(
                "Elexon returned invalid JSON: dataset=%s elapsed_seconds=%.2f",
                dataset,
                perf_counter() - started_at,
            )
            raise ElexonAPIError("Elexon returned invalid JSON", 502) from exc

        if isinstance(payload, dict):
            records = payload.get("data")
        else:
            records = payload

        if not isinstance(records, list):
            raise ElexonAPIError("Unexpected Elexon response structure")

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ElexonAPIError(
                    f"Invalid record at index {index}"
                )

            if any(field not in record for field in required_fields):
                raise ElexonAPIError(
                    f"Required fields missing from {dataset} record {index}"
                )

            timestamp_fields = (
                ("startTime", "publishTime")
                if dataset == "WINDFOR"
                else ("startTime",)
            )

            for field in timestamp_fields:
                value = record[field]
                if not isinstance(value, str):
                    raise ElexonAPIError(
                        f"Invalid {field} in {dataset} record {index}"
                    )
                try:
                    parsed = datetime.fromisoformat(
                        value.replace("Z", "+00:00")
                    )
                except ValueError as exc:
                    raise ElexonAPIError(
                        f"Invalid {field} in {dataset} record {index}"
                    ) from exc
                if parsed.tzinfo is None:
                    raise ElexonAPIError(
                        f"Timezone missing from {field} in {dataset} record {index}"
                    )

            generation = record["generation"]
            if (
                isinstance(generation, bool)
                or not isinstance(generation, (int, float))
            ):
                raise ElexonAPIError(
                    f"Invalid generation in {dataset} record {index}"
                )

        self._cache_records(cache_key, records)

        logger.info(
            "Elexon request completed: dataset=%s records=%d elapsed_seconds=%.2f",
            dataset,
            len(records),
            perf_counter() - started_at,
        )

        return deepcopy(records)
