from datetime import datetime
from datetime import timezone as tz

UTC = tz.utc
from typing import Any

import httpx


class PrometheusError(Exception):
    pass


class PrometheusUnavailable(PrometheusError):
    pass


class PrometheusMalformedResponse(PrometheusError):
    pass


class PrometheusClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def ready(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}/-/ready")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def instant_query(self, query: str) -> list[dict[str, Any]]:
        payload = await self._request("/api/v1/query", {"query": query})
        return self._results(payload, "vector")

    async def range_query(
        self, query: str, start: datetime, end: datetime, step: int
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "/api/v1/query_range",
            {"query": query, "start": start.timestamp(), "end": end.timestamp(), "step": step},
        )
        return self._results(payload, "matrix")

    async def _request(self, path: str, params: dict[str, str | float | int]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.base_url}{path}", params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise PrometheusUnavailable("Prometheus is unavailable.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "success"
            or not isinstance(payload.get("data"), dict)
        ):
            raise PrometheusMalformedResponse("Prometheus returned an invalid response.")
        return payload

    def _results(self, payload: dict[str, Any], expected_type: str) -> list[dict[str, Any]]:
        data = payload["data"]
        if data.get("resultType") != expected_type or not isinstance(data.get("result"), list):
            raise PrometheusMalformedResponse("Prometheus returned an unexpected result type.")
        return data["result"]


def parse_sample(sample: list[Any]) -> tuple[datetime, float]:
    if len(sample) != 2:
        raise PrometheusMalformedResponse("Prometheus sample is malformed.")
    try:
        return datetime.fromtimestamp(float(sample[0]), UTC), float(sample[1])
    except (TypeError, ValueError, OSError) as error:
        raise PrometheusMalformedResponse("Prometheus sample contains an invalid value.") from error
