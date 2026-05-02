"""
Location module for BT-7274.
Gets current geolocation from macOS CoreLocation or IP fallback.
"""

import json
import warnings
import requests
from typing import Optional, Tuple
from datetime import datetime, timedelta

# Suppress harmless pyobjc super() warning
warnings.filterwarnings("ignore", category=UserWarning, module="objc")

from bt7274_workstation.session_cache_manager import (
    save_location_cache,
    load_location_cache,
)


def _reverse_geocode(lat: float, lon: float) -> Tuple[str, str, str]:
    """Reverse geocode lat/lon to city/region/country using Open-Meteo API."""
    try:
        url = f"https://api.open-meteo.com/v1/search?latitude={lat}&longitude={lon}&count=1"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        results = data.get("results", [])
        if results:
            r = results[0]
            return (
                r.get("name", ""),
                r.get("admin1", ""),
                r.get("country", ""),
            )
    except Exception:
        pass
    return "", "", ""


class LocationProvider:
    def __init__(self, manual_location: dict = None):
        self._lat: Optional[float] = None
        self._lon: Optional[float] = None
        self._city: Optional[str] = None
        self._region: Optional[str] = None
        self._country: Optional[str] = None
        self._last_update: Optional[datetime] = None
        self._ttl_seconds = 300  # Cache location for 5 minutes
        self._manual = manual_location  # Optional manual override
        self._load_cached_location()

    def _load_cached_location(self):
        """Load last known location from session cache."""
        cached = load_location_cache()
        if cached:
            self._lat = cached.get("lat")
            self._lon = cached.get("lon")
            self._city = cached.get("city")
            self._region = cached.get("region")
            self._country = cached.get("country")
            # Parse timestamp to set _last_update so TTL logic works
            ts = cached.get("timestamp")
            if ts:
                try:
                    self._last_update = datetime.fromisoformat(ts)
                except Exception:
                    self._last_update = None

    def _save_location(self):
        """Persist current location to session cache."""
        save_location_cache(
            lat=self._lat,
            lon=self._lon,
            city=self._city or "",
            region=self._region or "",
            country=self._country or "",
        )

    def _is_stale(self) -> bool:
        if self._last_update is None:
            return True
        return (datetime.now() - self._last_update).total_seconds() > self._ttl_seconds

    def _get_macos_location(self) -> Optional[Tuple[float, float, str, str, str]]:
        """Try to get location via macOS CoreLocation using pyobjc."""
        try:
            from Foundation import NSObject, NSRunLoop, NSDate
            from CoreLocation import CLLocationManager
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                class LocationDelegate(NSObject):
                    def init(self):
                        self = super(LocationDelegate, self).init()
                        if self is None:
                            return None
                        self.location = None
                        self.error = None
                        return self

                    def locationManager_didUpdateLocations_(self, manager, locations):
                        if locations:
                            self.location = locations[-1]

                    def locationManager_didFailWithError_(self, manager, error):
                        self.error = error

                manager = CLLocationManager.alloc().init()
                delegate = LocationDelegate.alloc().init()
                manager.setDelegate_(delegate)
                manager.requestWhenInUseAuthorization()
                manager.startUpdatingLocation()

            # Wait briefly for location
            import time
            for _ in range(30):  # ~3 seconds
                if delegate.location or delegate.error:
                    break
                time.sleep(0.1)
                NSRunLoop.currentRunLoop().runUntilDate_(
                    NSDate.dateWithTimeIntervalSinceNow_(0.1)
                )

            manager.stopUpdatingLocation()

            if delegate.location:
                loc = delegate.location
                lat = loc.coordinate().latitude
                lon = loc.coordinate().longitude
                # Reverse geocode to get city/region
                city, region, country = _reverse_geocode(lat, lon)
                return lat, lon, city, region, country
        except Exception:
            pass
        return None

    def _get_ip_location(self) -> Optional[Tuple[float, float, str, str, str]]:
        """Fallback: get approximate location from IP geolocation API."""
        try:
            # Using ip-api.com (free, no key needed)
            resp = requests.get("http://ip-api.com/json/?fields=lat,lon,city,regionName,country", timeout=5)
            data = resp.json()
            if data.get("city"):
                return (
                    data.get("lat"),
                    data.get("lon"),
                    data.get("city", ""),
                    data.get("regionName", ""),
                    data.get("country", ""),
                )
        except Exception:
            pass
        return None

    def update(self) -> bool:
        """Refresh location data. Returns True if successful."""
        try:
            # Use manual override if provided
            if self._manual:
                self._lat = self._manual.get("lat")
                self._lon = self._manual.get("lon")
                self._city = self._manual.get("city", "")
                self._region = self._manual.get("region", "")
                self._country = self._manual.get("country", "")
                self._last_update = datetime.now()
                return True

            result = self._get_macos_location()
            if result is None:
                result = self._get_ip_location()

            if result:
                self._lat, self._lon, self._city, self._region, self._country = result
                self._last_update = datetime.now()
                self._save_location()
                return True
        except Exception as e:
            pass
        return False

    @property
    def location_str(self) -> str:
        """Human-readable location string."""
        try:
            if self._is_stale():
                self.update()
            parts = [p for p in [self._city, self._region, self._country] if p]
            if parts:
                return ", ".join(parts)
        except Exception:
            pass
        return "Unknown location"

    @property
    def lat_lon(self) -> Optional[Tuple[float, float]]:
        """Latitude and longitude tuple."""
        try:
            if self._is_stale():
                self.update()
            if self._lat is not None and self._lon is not None:
                return (self._lat, self._lon)
        except Exception:
            pass
        return None

    def enrich_query(self, query: str) -> str:
        """Add location context to a search query."""
        try:
            if self._is_stale():
                self.update()
            loc = self.location_str
            if loc and loc != "Unknown location":
                # Only add location if query doesn't already specify one
                lower = query.lower()
                if not any(x in lower for x in ["in ", "near ", "at ", "around "]):
                    return f"{query} in {loc}"
        except Exception:
            pass
        return query
