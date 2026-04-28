# BT-7274 Location Services

## Overview

The Location Provider is BT-7274's navigation subsystem. It determines the Pilot's current geographic position using macOS CoreLocation (primary) or IP geolocation (fallback), then enriches queries with local context for weather, travel, and search.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  macOS          │     │  LocationProvider│     │  Open-Meteo     │
│  CoreLocation   │────▶│  (5 min cache)  │────▶│  Reverse Geocode│
│  (pyobjc)       │     │                 │     │  (free, no key) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │
         │ (fallback)            │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  ip-api.com     │     │  Pipeline /     │
│  IP Geolocation │     │  Actions        │
│  (free, no key) │     │  (lat/lon/city) │
└─────────────────┘     └─────────────────┘
```

---

## Data Sources

### Primary: macOS CoreLocation

Uses `pyobjc` bindings to `CoreLocation.CLLocationManager`:
- Accuracy: ~10-100m
- Requires location permission
- Works offline after initial fix

### Fallback: IP Geolocation

Uses `ip-api.com` (free, no API key):
- Accuracy: ~city-level
- Requires internet
- Used when CoreLocation fails or is denied

### Override: Manual Location

Set in `config.yaml` to bypass all detection:

```yaml
location:
  manual:
    lat: 50.9311
    lon: 5.3378
    city: "Hasselt"
    region: "Limburg"
    country: "Belgium"
```

---

## Caching

Location data is cached for **5 minutes** (`_ttl_seconds = 300`) to avoid repeated API calls and permission prompts.

---

## Query Enrichment

The `enrich_query()` method adds location context to search queries:

```python
# Input:  "What's the weather?"
# Output: "What's the weather? in Hasselt, Limburg, Belgium"
```

This ensures weather and travel responses are personalized without the Pilot needing to specify their location every time.

---

## Privacy Notes

- **No location data is logged** by the Location Provider itself
- Location is only used for real-time query enrichment
- IP geolocation is approximate and does not expose precise GPS coordinates
- Manual override is recommended for maximum privacy

---

## File Location

- **Source**: `bt7274_workstation/location.py`
- **Used by**: `pipeline.py`, `weather_monitor.py`, `actions.py`
