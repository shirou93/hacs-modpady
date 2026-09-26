"""Async client for the public mOdpady API."""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import urlsplit

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import API_BASE, IMPLEMENTATIONS_URL, TENANT_SUFFIX


class ModpadyApiError(Exception):
    """Raised when the remote service returns invalid data or an HTTP error."""


def _headers(city: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Origin": f"https://{city}{TENANT_SUFFIX}",
    }


async def _get_json(hass, url: str, *, headers: dict[str, str] | None = None):
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            return await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise ModpadyApiError(str(err)) from err


async def async_get_cities(hass) -> list[dict[str, str]]:
    """Return municipalities that currently publish an mOdpady link."""
    implementations = await _get_json(
        hass, IMPLEMENTATIONS_URL, headers={"Accept": "application/json"}
    )
    cities: dict[str, str] = {}
    for implementation in implementations:
        products = implementation.get("products")
        if not isinstance(products, dict):
            continue
        product_url = products.get("kiedyodpady_link")
        if not isinstance(product_url, str) or not product_url.strip():
            continue
        hostname = (urlsplit(product_url).hostname or "").lower()
        if not hostname.endswith(TENANT_SUFFIX):
            continue
        slug = hostname[: -len(TENANT_SUFFIX)]
        if slug and all(char.isalnum() or char == "-" for char in slug):
            cities[slug] = implementation.get("title") or slug
    return [
        {"value": slug, "label": f"{title} ({slug})"}
        for slug, title in sorted(cities.items(), key=lambda item: item[1].casefold())
    ]


async def async_get_localities(hass, city: str) -> list[dict]:
    return await _get_json(
        hass, f"{API_BASE}/territory/localities", headers=_headers(city)
    )


async def async_get_streets(hass, city: str, locality_id: str) -> list[dict]:
    return await _get_json(
        hass,
        f"{API_BASE}/territory/localities/{locality_id}/streets",
        headers=_headers(city),
    )


async def async_get_addresses(hass, city: str, locality_id: str, street_id: str) -> list[str]:
    return await _get_json(
        hass,
        f"{API_BASE}/territory/localities/{locality_id}/addresses/{street_id}",
        headers=_headers(city),
    )


async def async_get_schedule(hass, city: str, locality_id: str, street_id: str, address: str) -> dict:
    """Fetch the next 60 days and resolve waste type identifiers."""
    today = dt_util.now().date()
    payload = {
        "from": today.isoformat(),
        "to": (today + timedelta(days=60)).isoformat(),
        "queries": [
            {
                "localityId": locality_id,
                "streetId": street_id,
                "number": address,
                "propertyType": "",
                "buildingType": "",
            }
        ],
    }
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            f"{API_BASE}/schedules/find",
            headers={**_headers(city), "Content-Type": "application/json"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            response.raise_for_status()
            result = await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise ModpadyApiError(str(err)) from err

    occurrences = result.get("occurrences", [])
    if not occurrences:
        return {"schedule": []}

    waste_types = await _get_json(
        hass, f"{API_BASE}/waste-types", headers=_headers(city)
    )
    names_by_id = {item["id"]: item["name"] for item in waste_types}
    by_date: dict[str, set[str]] = {}
    for occurrence in occurrences:
        pickup_date = occurrence["when"][:10]
        by_date.setdefault(pickup_date, set()).add(
            names_by_id.get(occurrence["what"], "Nieznany rodzaj odpadów")
        )

    return {
        "schedule": [
            {"date": pickup_date, "waste_types": sorted(names)}
            for pickup_date, names in sorted(by_date.items())
        ]
    }

