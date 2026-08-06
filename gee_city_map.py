"""Interactive version of dehradun_gee_map.py for any place and any time range.

Prompts the user for a place name, a date range, and a maximum cloud-cover
percentage, geocodes the place with OpenStreetMap Nominatim (stdlib urllib
only - no new dependency, so no risk of hitting the DLL-blocking issue
documented in CLAUDE.md), then pulls a cloud-filtered Sentinel-2 median
composite over that place/time and writes an interactive Leaflet map HTML
with the same True Color / False Color NIR / SWIR / individual-band layers
as dehradun_map.html.

Run: python gee_city_map.py
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import ee

from dehradun_gee_map import BAND_LABELS, BANDS, add_ee_layer, authenticate

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires a descriptive User-Agent identifying the app.
USER_AGENT = "geeapproach-city-map/1.0 (personal GEE scripting project)"
DEFAULT_MAX_CLOUD_PERCENTAGE = 20


def geocode_place(place_name):
    """Look up a place name via Nominatim. Returns (bounds_coords, center, display_name)
    where bounds_coords is [minLon, minLat, maxLon, maxLat], or None if not found."""
    query = urllib.parse.urlencode({"q": place_name, "format": "json", "limit": 1})
    request = urllib.request.Request(
        f"{NOMINATIM_URL}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        results = json.loads(response.read().decode("utf-8"))

    if not results:
        return None

    result = results[0]
    south, north, west, east = (float(v) for v in result["boundingbox"])
    bounds_coords = [west, south, east, north]
    center = [float(result["lat"]), float(result["lon"])]
    return bounds_coords, center, result["display_name"]


def prompt_place():
    while True:
        place_name = input("Place name (e.g. 'Jaipur, India'): ").strip()
        if not place_name:
            continue
        try:
            geocoded = geocode_place(place_name)
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"Geocoding failed ({exc}). Check your internet connection and try again.")
            continue
        if geocoded is None:
            print(f"No location found for '{place_name}'. Try being more specific.")
            continue
        bounds_coords, center, display_name = geocoded
        print(f"Found: {display_name}")
        return bounds_coords, center, display_name, place_name


def prompt_date(label, default):
    while True:
        raw = input(f"{label} [{default}]: ").strip() or default
        try:
            datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            print("Please use YYYY-MM-DD format.")
            continue
        return raw


def prompt_max_cloud_percentage():
    while True:
        raw = input(
            f"Max cloudy-pixel percentage [{DEFAULT_MAX_CLOUD_PERCENTAGE}]: "
        ).strip() or str(DEFAULT_MAX_CLOUD_PERCENTAGE)
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        return value


def slugify(text):
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug or "place"


def get_city_image(bounds_coords, start_date, end_date, max_cloud_percentage):
    bounds = ee.Geometry.Rectangle(bounds_coords)
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(bounds)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_percentage))
    )
    image_count = collection.size().getInfo()
    composite = collection.median().select(BANDS)
    return composite.clip(bounds), image_count


def build_map(image, center):
    import folium

    m = folium.Map(location=center, zoom_start=11)

    add_ee_layer(
        m, image, {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000},
        "True Color (B4-B3-B2)",
    )
    add_ee_layer(
        m, image, {"bands": ["B8", "B4", "B3"], "min": 0, "max": 3000},
        "False Color NIR (B8-B4-B3)",
    )
    add_ee_layer(
        m, image, {"bands": ["B12", "B11", "B4"], "min": 0, "max": 3000},
        "SWIR (B12-B11-B4)",
    )

    for band in BANDS:
        vis = {"bands": [band], "min": 0, "max": 3000, "palette": ["black", "white"]}
        add_ee_layer(m, image, vis, f"{band} - {BAND_LABELS[band]}")

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def main():
    bounds_coords, center, display_name, place_name = prompt_place()
    start_date = prompt_date("Start date", "2024-01-01")
    end_date = prompt_date("End date", "2024-12-31")
    max_cloud_percentage = prompt_max_cloud_percentage()

    authenticate()
    image, image_count = get_city_image(bounds_coords, start_date, end_date, max_cloud_percentage)
    if image_count == 0:
        print(
            "Warning: no Sentinel-2 scenes matched that date range/cloud threshold "
            "for this area - the map layers will be blank. Try a wider date range "
            "or a higher max cloud percentage."
        )
    else:
        print(f"Found {image_count} Sentinel-2 scene(s) matching the filters.")

    m = build_map(image, center)
    output_html = os.path.join(os.path.dirname(__file__), f"{slugify(place_name)}_map.html")
    m.save(output_html)
    print(f"Saved map to {output_html}")


if __name__ == "__main__":
    main()
