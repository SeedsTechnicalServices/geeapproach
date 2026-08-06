"""Fetch Sentinel-2 imagery for Dehradun from Google Earth Engine and render
an interactive HTML map showing several band combinations.

Uses the service account key already present in this folder to authenticate,
so it can run non-interactively (no browser login prompt).
"""

import os

import ee
import folium

SERVICE_ACCOUNT = "anurag@gisproject-503012.iam.gserviceaccount.com"
KEY_FILE = os.path.join(os.path.dirname(__file__), "gisproject-503012-b7a893527fcb.json")
PROJECT_ID = "gisproject-503012"
OUTPUT_HTML = os.path.join(os.path.dirname(__file__), "dehradun_map.html")

# Rough bounding box around Dehradun, Uttarakhand.
DEHRADUN_BOUNDS_COORDS = [77.90, 30.20, 78.15, 30.45]
DEHRADUN_CENTER = [30.3165, 78.0322]

BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
BAND_LABELS = {
    "B2": "Blue",
    "B3": "Green",
    "B4": "Red",
    "B8": "NIR",
    "B11": "SWIR1",
    "B12": "SWIR2",
}


def authenticate():
    credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_FILE)
    ee.Initialize(credentials, project=PROJECT_ID)


def get_dehradun_image():
    bounds = ee.Geometry.Rectangle(DEHRADUN_BOUNDS_COORDS)
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(bounds)
        .filterDate("2024-01-01", "2024-12-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
    )
    composite = collection.median().select(BANDS)
    return composite.clip(bounds)


def add_ee_layer(folium_map, image, vis_params, name):
    map_id_dict = image.getMapId(vis_params)
    folium.TileLayer(
        tiles=map_id_dict["tile_fetcher"].url_format,
        attr="Google Earth Engine",
        name=name,
        overlay=True,
        control=True,
    ).add_to(folium_map)


def build_map(image):
    m = folium.Map(location=DEHRADUN_CENTER, zoom_start=11)

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
    authenticate()
    image = get_dehradun_image()
    m = build_map(image)
    m.save(OUTPUT_HTML)
    print(f"Saved map to {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
