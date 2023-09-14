from __future__ import annotations

import asyncio
import datetime
import json
import socket
from collections import OrderedDict
from typing import Any, Literal
from urllib.parse import urlencode

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

    async def get_weather_data(
        self,
        lat: float,
        lon: float,
        data_sets: list[DataSetType] = [DataSetType.CURRENT_WEATHER],
        hourly_start: datetime.datetime | None = None,
        hourly_end: datetime.datetime | None = None,
        lang: str = "en-US"
    ) -> Any:
        hourly_start = hourly_start or datetime.datetime.utcnow()
        hourly_end = hourly_end or datetime.datetime.utcnow() + datetime.timedelta(days=1)
        token = self._generate_jwt()
        query = urlencode(
            OrderedDict(
                dataSets=",".join(data_sets),
                hourlyStart=hourly_start.isoformat() + "Z",
                hourlyEnd=hourly_end.isoformat() + "Z",
            )
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
                "iat": datetime.datetime.utcnow(),
                "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
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
        try:
            async with async_timeout.timeout(10):
                response = await self._session.request(
                    method=method,
                    url=url,
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
                "Timeout error fetching information",
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise WeatherKitApiClientCommunicationError(
                "Error fetching information",
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            raise WeatherKitApiClientError(
                "Something really wrong happened!"
            ) from exception
