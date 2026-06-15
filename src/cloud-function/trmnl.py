"""Google Cloud Function: Norwegian public-transport departures for TRMNL.

Fetches live departures from the Entur Journey Planner GraphQL API, groups them
by line and destination, and returns a template-ready JSON payload that a TRMNL
polling plugin renders on an e-ink display.

Configuration via environment variables (all optional):
  ENTUR_CLIENT_NAME  ET-Client-Name header value (default "trmnl-norway-departures")
  API_SECRET         if set, callers must pass ?secret=<value>; if unset, open
  DEFAULT_STOP       fallback Entur stop id (default Jernbanetorget)

Query parameters:
  stop               Entur stop id, e.g. NSR:StopPlace:58366
  exclude_platforms  comma-separated platform/quay codes to hide, e.g. "A,B"
  minutes_to_fetch   size of the departure window in minutes (default 30)
  ignore_minutes     skip departures within the next N minutes (default 3)
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from collections import defaultdict
from zoneinfo import ZoneInfo

import functions_framework
import requests
from flask import Request, jsonify

logger = logging.getLogger(__name__)

ENTUR_GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
ENTUR_CLIENT_NAME = os.environ.get("ENTUR_CLIENT_NAME", "trmnl-norway-departures")
API_SECRET = os.environ.get("API_SECRET")
DEFAULT_STOP = os.environ.get("DEFAULT_STOP", "NSR:StopPlace:58366")  # Jernbanetorget

OSLO = ZoneInfo("Europe/Oslo")
REQUEST_TIMEOUT = 10  # seconds
FETCH_LIMIT = 200  # max departures requested from Entur per call

# GraphQL variables keep the query injection-safe (no f-string interpolation).
DEPARTURES_QUERY = """
query Departures($stop: String!, $start: DateTime!, $range: Int!, $limit: Int!) {
  stopPlace(id: $stop) {
    name
    estimatedCalls(
      startTime: $start
      timeRange: $range
      numberOfDepartures: $limit
      arrivalDeparture: departures
      whiteListedModes: [rail, bus, metro, tram, water, coach]
      includeCancelledTrips: false
    ) {
      expectedDepartureTime
      destinationDisplay { frontText }
      quay { publicCode }
      serviceJourney { line { publicCode transportMode } }
    }
  }
}
"""


def parse_int(value: str | None, default: int) -> int:
    """Parse a query-string int, falling back to a default on bad input."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def to_hhmm(iso_timestamp: str) -> str:
    """2026-06-15T12:04:00+02:00 -> 12:04 (in the timestamp's own offset)."""
    return dt.datetime.fromisoformat(iso_timestamp).strftime("%H:%M")


def line_sort_key(line_code: str) -> tuple[int, object]:
    """Numeric local lines (5, 17) first, then lettered/regional (FB1, 31E)."""
    return (0, int(line_code)) if line_code.isdigit() else (1, line_code)


def fetch_departures(stop: str, start_iso: str, time_range: int) -> tuple[str, list[dict]]:
    """Return (station_name, estimated_calls) from Entur. Raises on failure."""
    response = requests.post(
        ENTUR_GRAPHQL_URL,
        json={
            "query": DEPARTURES_QUERY,
            "variables": {
                "stop": stop,
                "start": start_iso,
                "range": time_range,
                "limit": FETCH_LIMIT,
            },
        },
        headers={"ET-Client-Name": ENTUR_CLIENT_NAME},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    body = response.json()

    if body.get("errors"):
        raise ValueError(f"Entur GraphQL errors: {body['errors']}")

    stop_place = body["data"]["stopPlace"]
    if stop_place is None:
        raise ValueError(f"Unknown stop id: {stop}")
    return stop_place["name"], stop_place["estimatedCalls"]


def build_lines(calls: list[dict], exclude_platforms: str) -> list[dict]:
    """Group calls into a sorted, template-ready list of lines and destinations."""
    excluded = {p.strip() for p in exclude_platforms.split(",") if p.strip()}

    # line_code -> {(destination, platform): [times]}
    grouped: dict[str, dict[tuple[str, str | None], list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    modes: dict[str, str] = {}

    for call in calls:
        platform = (call.get("quay") or {}).get("publicCode")
        if platform in excluded:
            continue
        line = call["serviceJourney"]["line"]
        line_code = line["publicCode"]
        destination = call["destinationDisplay"]["frontText"]
        grouped[line_code][(destination, platform)].append(
            to_hhmm(call["expectedDepartureTime"])
        )
        modes[line_code] = line["transportMode"]

    lines = []
    for line_code in sorted(grouped, key=line_sort_key):
        destinations = [
            {
                "destination": destination,
                "platform": platform or "",
                "times": times,
            }
            for (destination, platform), times in sorted(
                grouped[line_code].items(), key=lambda kv: (kv[0][1] or "", kv[0][0])
            )
        ]
        lines.append(
            {"line": line_code, "mode": modes[line_code], "destinations": destinations}
        )
    return lines


def build_payload(stop: str, exclude_platforms: str, window_minutes: int, lead_minutes: int) -> dict:
    """Fetch and assemble the full TRMNL payload for one stop."""
    start = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=lead_minutes)
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")

    station, calls = fetch_departures(stop, start_iso, window_minutes * 60)
    lines = build_lines(calls, exclude_platforms)
    shown = sum(len(dest["times"]) for line in lines for dest in line["destinations"])

    return {
        "station": station,
        "window_minutes": window_minutes,
        "total": len(calls),
        "shown": shown,
        "last_updated": dt.datetime.now(OSLO).strftime("%H:%M"),
        "lines": lines,
    }


@functions_framework.http
def http(request: Request):
    """HTTP entry point. Returns the departures payload as JSON."""
    if API_SECRET and request.args.get("secret") != API_SECRET:
        return ("Forbidden", 403)

    stop = request.args.get("stop") or DEFAULT_STOP
    exclude_platforms = request.args.get("exclude_platforms", "")
    window_minutes = parse_int(request.args.get("minutes_to_fetch"), 30)
    lead_minutes = parse_int(request.args.get("ignore_minutes"), 3)

    try:
        payload = build_payload(stop, exclude_platforms, window_minutes, lead_minutes)
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.exception("Failed to fetch departures from Entur")
        return jsonify({"error": str(exc), "station": "", "lines": []}), 502

    return jsonify(payload)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json

    print(json.dumps(build_payload(DEFAULT_STOP, "", 30, 3), ensure_ascii=False, indent=2))
