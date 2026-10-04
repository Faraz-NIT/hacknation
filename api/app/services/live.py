"""Live-data adapters with snapshot + cache fallback.

Rules (from the technical plan, section 5):
  * fetch once at session start and freeze the result into the case snapshot
  * persist the raw provider response next to the normalized projection
  * on failure fall back to the most recent cache and label it "cached HH:MM"
  * external data never triggers an action; it only informs the human

Every adapter returns (normalized_payload | None, provenance_label).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import logging

import httpx

from ..db import DATA_DIR

log = logging.getLogger("skymentor")

CACHE_DIR = DATA_DIR / "cache"
TIMEOUT = float(os.environ.get("LIVE_TIMEOUT_S", "6"))

AIRPORTS = {
    "CDG": (49.0097, 2.5479), "FRA": (50.0379, 8.5622), "HND": (35.5494, 139.7798),
    "DOH": (25.2731, 51.6081), "LHR": (51.4700, -0.4543), "HEL": (60.3172, 24.9633),
    "AMS": (52.3105, 4.7683), "JFK": (40.6413, -73.7781), "KEF": (63.9850, -22.6056),
    "DUB": (53.4264, -6.2499), "MUC": (48.3537, 11.7750),
}


# ------------------------------------------------------------------------ cache
def _cache_path(provider: str, key: str) -> Path:
    safe = "".join(ch if ch.isalnum() else "_" for ch in key)
    return CACHE_DIR / f"{provider}_{safe}.json"


def _save(provider: str, key: str, raw: Any, normalized: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(provider, key).write_text(
        json.dumps({"fetched_at": time.time(), "raw": raw, "normalized": normalized}, default=str)
    )


def _load(provider: str, key: str) -> tuple[Optional[Any], str]:
    path = _cache_path(provider, key)
    if not path.exists():
        return None, "unavailable"
    blob = json.loads(path.read_text())
    when = datetime.fromtimestamp(blob["fetched_at"]).strftime("%H:%M")
    return blob["normalized"], f"cached {when}"


# ---------------------------------------------------------------------- weather
def weather_features(raw_current: dict[str, Any]) -> dict[str, Any]:
    wind = float(raw_current.get("wind_speed_10m") or 0)
    gust = float(raw_current.get("wind_gusts_10m") or 0)
    precip = float(raw_current.get("precipitation") or 0)
    snow = float(raw_current.get("snowfall") or 0)
    risk = "normal"
    if wind >= 45 or gust >= 65 or precip >= 4 or snow > 0.5:
        risk = "elevated"
    if wind >= 70 or gust >= 90 or snow > 3:
        risk = "severe"
    return {
        "temp_c": raw_current.get("temperature_2m"),
        "wind_kph": round(wind),
        "gust_kph": round(gust),
        "precip_mm": precip,
        "risk": risk,
    }


def get_weather(iata: str) -> tuple[Optional[dict[str, Any]], str]:
    if iata not in AIRPORTS:
        return None, "unknown airport"
    lat, lon = AIRPORTS[iata]
    try:
        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,precipitation,snowfall,wind_speed_10m,wind_gusts_10m",
                "wind_speed_unit": "kmh",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        raw = r.json()
        norm = weather_features(raw.get("current", {}))
        _save("weather", iata, raw, norm)
        return norm, "live"
    except Exception:
        return _load("weather", iata)


# ---------------------------------------------------------------- flight status
def normalize_aviationstack(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    data = raw.get("data") or []
    if not data:
        return None
    f = data[0]
    dep, arr = f.get("departure") or {}, f.get("arrival") or {}
    return {
        "status": f.get("flight_status") or "unknown",
        "delay_min": dep.get("delay") or arr.get("delay"),
        "scheduled_arrival": (arr.get("scheduled") or "")[11:16] or None,
        "airline": (f.get("airline") or {}).get("name"),
    }


def get_flight_status(flight_iata: str) -> tuple[Optional[dict[str, Any]], str]:
    key = os.environ.get("AVIATIONSTACK_KEY")
    if not key:
        cached, label = _load("status", flight_iata)
        return cached, label if cached else "no key"
    try:
        # Free plan is HTTP-only; paid plans accept HTTPS.
        base = os.environ.get("AVIATIONSTACK_BASE", "http://api.aviationstack.com/v1")
        r = httpx.get(f"{base}/flights", params={"access_key": key, "flight_iata": flight_iata}, timeout=TIMEOUT)
        r.raise_for_status()
        raw = r.json()
        norm = normalize_aviationstack(raw)
        if norm is None:
            raise ValueError("empty aviationstack response")
        _save("status", flight_iata, raw, norm)
        return norm, "live"
    except Exception:
        return _load("status", flight_iata)


# --------------------------------------------------------------- itineraries
def _first(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def normalize_brightdata(raw: Any) -> list[dict[str, Any]]:
    """Best-effort projection of a Bright Data Google Flights record list.

    Dataset schemas differ by collector; adjust the key lists below to match the
    dataset you configure. Anything that cannot be parsed is skipped.
    """
    records = raw if isinstance(raw, list) else (raw.get("data") or raw.get("results") or [])
    flat: list[dict[str, Any]] = []
    for rec in records:
        if isinstance(rec, dict) and isinstance(rec.get("flights"), list):
            flat.extend(x for x in rec["flights"] if isinstance(x, dict))
        elif isinstance(rec, dict):
            flat.append(rec)
    out: list[dict[str, Any]] = []
    for i, f in enumerate(flat[:8]):
        price = _first(f, "price", "price_eur", "total_price", "final_price")
        if isinstance(price, str):
            digits = "".join(ch for ch in price if ch.isdigit())
            price = int(digits) if digits else None
        layovers = f.get("layovers") or f.get("stops_info") or []
        hub = None
        conn_min = None
        if isinstance(layovers, list) and layovers:
            lay = layovers[0] if isinstance(layovers[0], dict) else {}
            hub = _first(lay, "id", "airport_code", "iata", "airport")
            conn_min = _first(lay, "duration", "duration_min", "layover_minutes")
        if price is None:
            continue
        out.append({
            "id": chr(ord("A") + i),
            "label": f"via {hub}" if hub else "Nonstop",
            "hub": hub or "-",
            "hub_city": hub or "Nonstop",
            "carrier": _first(f, "airline", "carrier", "airlines") or "Unknown",
            "alliance": "",
            "departure": str(_first(f, "departure_time", "departure") or "")[-5:],
            "arrival": str(_first(f, "arrival_time", "arrival") or "")[-5:],
            "connection_min": int(conn_min or 0),
            "price_eur": int(price),
            "cabin": "economy",
        })
    return out


# ---------------------------------------------------------- Google Flights (free)
GOOGLE_FLIGHTS_URL = "https://www.google.com/travel/flights"
# Pre-accepted consent: without it, EU traffic gets the "Before you continue" page.
GOOGLE_CONSENT = {"SOCS": "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg", "CONSENT": "YES+cb"}


def _configured(value: Optional[str]) -> bool:
    return bool(value) and not value.startswith("your-")


def brightdata_configured() -> bool:
    return _configured(os.environ.get("BRIGHTDATA_API_TOKEN")) and _configured(os.environ.get("BRIGHTDATA_FLIGHTS_DATASET_ID"))


def google_flights_enabled() -> bool:
    if os.environ.get("FARES_SOURCE", "google") != "google":
        return False
    try:
        import fast_flights  # noqa: F401
    except ImportError:
        return False
    return True


def _hhmm_pair(value: Any) -> str:
    padded = [*(value or []), None, None]  # Google omits zero components: [8] = 08:00
    return f"{padded[0] or 0:02d}:{padded[1] or 0:02d}"


def parse_google_flights(html: str) -> list[dict[str, Any]]:
    """Itineraries from the Google Flights results page (the `ds:1` data blob).

    Same payload layout as the fast-flights parser, but itineraries with a
    missing price or odd shape are skipped instead of failing the whole page.
    """
    marker = html.find("AF_initDataCallback({key: 'ds:1'")
    if marker < 0:
        raise ValueError("no ds:1 payload (consent page or layout change)")
    blob = html[marker:].split("data:", 1)[1]
    payload, _ = json.JSONDecoder().raw_decode(blob)
    out: list[dict[str, Any]] = []
    for item in (payload[3][0] or []) if payload[3] else []:
        try:
            itin, price = item[0], item[1][0][1]
            legs = itin[2]
            stops = []
            for prev, nxt in zip(legs, legs[1:]):
                arr = datetime(*prev[21], *[int(x) for x in _hhmm_pair(prev[10]).split(":")])
                dep = datetime(*nxt[20], *[int(x) for x in _hhmm_pair(nxt[8]).split(":")])
                stops.append({"hub": prev[6], "hub_city": _short_airport(prev[5]), "minutes": int((dep - arr).total_seconds() // 60)})
            out.append({
                "price_eur": int(price), "airlines": list(itin[1]), "stops": stops,
                "departure": _hhmm_pair(legs[0][8]), "arrival": _hhmm_pair(legs[-1][10]),
                "overnight": tuple(legs[-1][21]) != tuple(legs[0][20]),
            })
        except (IndexError, TypeError, ValueError):
            continue
    return out


def _short_airport(name: str) -> str:
    for suffix in (" International Airport", " Airport", " International"):
        name = name.replace(suffix, "")
    return name.strip()


def normalize_google_flights(itineraries: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    out = []
    for i, it in enumerate(itineraries[:limit]):
        stops = it["stops"]
        shortest = min(stops, key=lambda s: s["minutes"]) if stops else None  # riskiest connection
        notes = [f"{len(stops)} stops" if len(stops) > 1 else "", "+1 day" if it["overnight"] else ""]
        out.append({
            "id": chr(ord("A") + i),
            "label": f"via {' + '.join(s['hub_city'] for s in stops)}" if stops else "Nonstop",
            "hub": shortest["hub"] if shortest else "-",
            "hub_city": shortest["hub_city"] if shortest else "Nonstop",
            "carrier": ", ".join(it["airlines"]) or "Unknown",
            "alliance": "",
            "departure": it["departure"],
            "arrival": it["arrival"],
            "connection_min": shortest["minutes"] if shortest else 0,
            "price_eur": it["price_eur"],
            "cabin": "economy",
            "note": ", ".join(n for n in notes if n) or None,
        })
    return out


def search_google_flights(origin: str, destination: str, date: str) -> list[dict[str, Any]]:
    """Free Google Flights search: fast-flights builds the query, we fetch and parse."""
    import fast_flights as ff
    from primp import Client

    query = ff.create_query(flights=[ff.FlightQuery(date=date, from_airport=origin, to_airport=destination)],
                            trip="one-way", currency="EUR", checked_bags=1)
    client = Client(impersonate="chrome_145", impersonate_os="macos", referer=True, cookie_store=True,
                    timeout=float(os.environ.get("GOOGLE_FLIGHTS_TIMEOUT_S", "15")))
    client.set_cookies("https://www.google.com", GOOGLE_CONSENT)
    html = client.get(GOOGLE_FLIGHTS_URL, params={**query.params(), "hl": "en", "gl": "us"}).text
    return parse_google_flights(html)


def search_alternatives(origin: str, destination: str, date: Optional[str] = None) -> tuple[Optional[list[dict[str, Any]]], str]:
    """Live public fares: Bright Data if configured, else free Google Flights, else cache."""
    key = f"{origin}_{destination}"
    date = date or (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    if not brightdata_configured():
        if not google_flights_enabled():
            cached, label = _load("flights", key)
            return cached, label if cached else "no source"
        try:
            raw = search_google_flights(origin, destination, date)
            norm = normalize_google_flights(raw)
            if len(norm) < 2:
                raise ValueError("too few itineraries parsed")
            _save("flights", key, raw, norm)
            return norm, "live"
        except Exception as exc:
            log.warning("google flights failed for %s: %s", key, exc)
            return _load("flights", key)
    token = os.environ.get("BRIGHTDATA_API_TOKEN")
    dataset = os.environ.get("BRIGHTDATA_FLIGHTS_DATASET_ID")
    template = os.environ.get(
        "BRIGHTDATA_FLIGHTS_INPUT",
        '[{"url": "https://www.google.com/travel/flights?q=Flights%20from%20{origin}%20to%20{destination}%20on%20{date}%20one%20way"}]',
    )
    body = json.loads(template.replace("{origin}", origin).replace("{destination}", destination).replace("{date}", date))
    try:
        r = httpx.post(
            "https://api.brightdata.com/datasets/v3/scrape",
            params={"dataset_id": dataset, "format": "json"},
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=float(os.environ.get("BRIGHTDATA_TIMEOUT_S", "45")),
        )
        r.raise_for_status()
        raw = r.json()
        norm = normalize_brightdata(raw)
        if len(norm) < 2:
            raise ValueError("too few itineraries parsed")
        _save("flights", key, raw, norm)
        return norm, "live"
    except Exception:
        return _load("flights", key)
