from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from aiohttp_retry import RetryClient, ExponentialRetry

import aiohttp
import async_timeout
import jwt

from . import DataSetType


class WeatherKitApiClientError(Exception):
    """Exception to indicate a general API error."""


class WeatherKitApiClientCommunicationError(WeatherKitApiClientError):
    """Exception to indicate a communication error."""


class WeatherKitApiClientAuthenticationError(WeatherKitApiClientError):
    """Exception to indicate an authentication error."""


class WeatherKitApiClient:
    def __init__(
        self,
        key_id: str,
        service_id: str,
        team_id: str,
        key_pem: str,
        session: aiohttp.ClientSession | None,
    ) -> None:
        self._key_id = key_id
        self._service_id = service_id
        self._team_id = team_id
        self._key_pem = key_pem
        self._session = session
        self._client = None # lazy loaded

    async def get_weather_data(
        self,
        lat: float,
        lon: float,
        data_sets: list[DataSetType] = [DataSetType.CURRENT_WEATHER],
        hourly_start: datetime | None = None,
        hourly_end: datetime | None = None,
        lang: str = "en-US"
    ) -> Any:
        hourly_start = hourly_start or datetime.now(tz=UTC)
        hourly_end = hourly_end or datetime.now(tz=UTC) + timedelta(days=1)
        if hourly_start.tzinfo:
            hourly_start = hourly_start.astimezone(tz=UTC).replace(tzinfo=None)
        if hourly_end.tzinfo:
            hourly_end = hourly_end.astimezone(tz=UTC).replace(tzinfo=None)

        token = self._generate_jwt()
        query = urlencode(
            {
                "dataSets": ",".join(data_sets),
                "hourlyStart": f"{hourly_start.isoformat()}Z",
                "hourlyEnd": f"{hourly_end.isoformat()}Z",
            }
        )

        return await self._api_wrapper(
            method="get",
            url=f"https://weatherkit.apple.com/api/v1/weather/{lang}/{lat}/{lon}?{query}",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def get_availability(self, lat: float, lon: float) -> list[DataSetType]:
        """Determine availability of different weather data sets."""
        token = self._generate_jwt()
        return await self._api_wrapper(
            method="get",
            url=f"https://weatherkit.apple.com/api/v1/availability/{lat}/{lon}",
            headers={"Authorization": f"Bearer {token}"},
        )

    def _generate_jwt(self) -> str:
        return jwt.encode(
            {
                "iss": self._team_id,
                "iat": datetime.now(tz=UTC),
                "exp": datetime.now(tz=UTC) + timedelta(minutes=10),
                "sub": self._service_id,
            },
            self._key_pem,
            headers={"kid": self._key_id, "id": f"{self._team_id}.{self._service_id}"},
            algorithm="ES256",
        )

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
    ) -> Any:
        """Get information from the API."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

        if self._client is None:
            retry_options = ExponentialRetry(
                attempts=3,
                statuses=(404, 401, 403), # automatically includes any 5xx errors
                start_timeout=1,
            )
            self._client = RetryClient(retry_options=retry_options, client_session=self._session)

        try:
            async with async_timeout.timeout(20):
                response = await self._client.request(
                    method=method,
                    url=url,
                    raise_for_status=True,
                    headers=headers,
                    json=data,
                )

                if response.status in (401, 403):
                    body = await response.text()
                    raise WeatherKitApiClientAuthenticationError(
                        f"Invalid credentials: {body}",
                    )

                response.raise_for_status()
                return await response.json()

        except WeatherKitApiClientAuthenticationError as exception:
            raise exception
        except asyncio.TimeoutError as exception:
            raise WeatherKitApiClientCommunicationError(
                f"Timeout error fetching information: {exception}",
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise WeatherKitApiClientCommunicationError(
                f"Error fetching information: {exception}",
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            raise WeatherKitApiClientError(
                f"An unexpected error occurred: {exception}"
            ) from exception
