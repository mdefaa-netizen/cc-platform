"""
Mileage + stipend math — single source of truth.

The distance helpers (Google Maps Distance Matrix + OpenStreetMap/Haversine
fallback) were lifted verbatim from pages/7_Payments.py:341-403 so that page,
the host/facilitator portal, and any future surface compute the same numbers.

Constants here are program-wide and locked:
- MILEAGE_RATE is the 2026 IRS standard rate; it can still be overridden per
  reimbursement in the Payments calculator UI (kept for back-compat with the
  existing rate-input control in pages/7_Payments.py).
- FACILITATOR_STIPEND is the program stipend per facilitator and is NOT
  user-editable in the UI; it intentionally replaces the per-facilitator
  payment_amount as the source of truth for the stipend portion of the
  Payments summary.
"""
from __future__ import annotations

import math

import requests
import streamlit as st


MILEAGE_RATE = 0.725
FACILITATOR_STIPEND = 400.0


def get_maps_api_key() -> str:
    """Read GOOGLE_MAPS_API_KEY from st.secrets; fall back to the per-session
    key saved by the Payments page Settings sub-tab. Returns '' when neither
    is set — the caller should then use the OpenStreetMap fallback."""
    try:
        return st.secrets.get("GOOGLE_MAPS_API_KEY", "")
    except Exception:
        return st.session_state.get("google_maps_key", "")


def calculate_distance_google(origin: str, destination: str, api_key: str):
    """Google Maps Distance Matrix — driving miles. Returns
    (distance_miles, distance_text, None) on success or (None, None, error).
    Behavior identical to the prior pages/7_Payments.py implementation."""
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "units": "imperial",
        "mode": "driving",
        "key": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data["status"] == "OK":
            element = data["rows"][0]["elements"][0]
            if element["status"] == "OK":
                distance_text = element["distance"]["text"]
                distance_miles = element["distance"]["value"] / 1609.344
                return distance_miles, distance_text, None
            else:
                return None, None, f"Route not found: {element['status']}"
        else:
            return None, None, f"API error: {data['status']}"
    except Exception as e:
        return None, None, str(e)


def calculate_distance_fallback(origin: str, destination: str):
    """OpenStreetMap Nominatim geocode + Haversine × 1.2 road-routing fudge.
    No API key required. Returns the same triple as the Google path."""
    def _geocode(address):
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "CCPlatform/1.0"}
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            results = r.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception:
            pass
        return None, None

    lat1, lon1 = _geocode(origin)
    lat2, lon2 = _geocode(destination)

    if not all([lat1, lon1, lat2, lon2]):
        return None, None, "Could not geocode one or both addresses."

    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c * 1.2  # +20% for road routing vs straight line
    return distance, f"~{distance:.1f} mi (estimated)", None


def calculate_round_trip_miles(origin: str, destination: str):
    """Round-trip driving miles for a facilitator → event-venue trip.

    Prefers Google Maps when GOOGLE_MAPS_API_KEY is configured, otherwise
    uses the OpenStreetMap/Haversine fallback. Returns
    (round_trip_miles, text, None) on success or (None, None, error).
    """
    if not origin or not destination:
        return None, None, "Both origin and destination are required."
    api_key = get_maps_api_key()
    if api_key:
        one_way, text, err = calculate_distance_google(origin, destination, api_key)
    else:
        one_way, text, err = calculate_distance_fallback(origin, destination)
    if err or one_way is None:
        return None, None, err or "Distance unavailable."
    return one_way * 2, text, None


def estimate_reimbursement(round_trip_miles: float) -> dict:
    """Apply the program formula: mileage = round_trip * MILEAGE_RATE; stipend
    is the locked program constant; total = mileage + stipend."""
    miles = float(round_trip_miles or 0)
    mileage = miles * MILEAGE_RATE
    return {
        "mileage": mileage,
        "stipend": FACILITATOR_STIPEND,
        "total": mileage + FACILITATOR_STIPEND,
    }
