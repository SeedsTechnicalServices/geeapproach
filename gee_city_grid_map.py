"""Vector/GeoJSON version of gee_city_map.py.

gee_city_map.py displays Sentinel-2 imagery as raster PNG map tiles rendered
by Earth Engine's tile server (image.getMapId() -> folium.TileLayer) - fast
and full-resolution, but the pixel data itself never reaches this script as
GeoJSON or any other file.

This script instead vectorizes the same composite into a grid of small
rectangular cells (ee.Geometry.coveringGrid), computes the mean of each band
inside every cell server-side (image.reduceRegions), and pulls the result
back as a real GeoJSON FeatureCollection (reduced.getInfo()) - one Feature
per cell, carrying the band means as properties. That GeoJSON is:
  1. written to disk as a standalone <place>_grid.geojson file, and
  2. rendered into <place>_grid_map.html as toggleable colored-cell layers
     (one per band combination, matching dehradun_map.html's layer set),
     with a popup on each cell showing its exact band values.

Trade-off vs. gee_city_map.py: cell size controls detail. Fine cells (e.g.
100m) closely approximate the raster but can produce tens of thousands of
cells for a whole city - Earth Engine's reduceRegions/getInfo() can't
reliably return that many features in one call, and a browser can't render
that many polygons smoothly either. This script computes the actual cell
count for the requested size first and automatically coarsens the grid if
it would exceed MAX_GRID_CELLS, printing what it did and why.

Run: python gee_city_grid_map.py
"""

import json
import math
import os

import ee
import folium

from dehradun_gee_map import BAND_LABELS, BANDS, authenticate
from gee_city_map import (
    get_city_image,
    prompt_date,
    prompt_max_cloud_percentage,
    prompt_place,
    slugify,
)

# Keeps Earth Engine's reduceRegions().getInfo() call (which has practical
# interactive size limits) and the rendered HTML (each of the 9 layers below
# embeds its own copy of every cell's geometry) both reliably fast.
MAX_GRID_CELLS = 2000
DEFAULT_CELL_SIZE_METERS = 100
VIS_MIN = 0
VIS_MAX = 3000

# (layer name, bands to combine, is_composite) - mirrors dehradun_gee_map.py's
# build_map() layer set exactly, just rendered as colored cells instead of tiles.
LAYERS = [
    ("True Color (B4-B3-B2)", ["B4", "B3", "B2"]),
    ("False Color NIR (B8-B4-B3)", ["B8", "B4", "B3"]),
    ("SWIR (B12-B11-B4)", ["B12", "B11", "B4"]),
] + [(f"{band} - {BAND_LABELS[band]}", [band]) for band in BANDS]


def prompt_cell_size_meters():
    while True:
        raw = input(
            f"Grid cell size in meters [{DEFAULT_CELL_SIZE_METERS}]: "
        ).strip() or str(DEFAULT_CELL_SIZE_METERS)
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if value <= 0:
            print("Cell size must be positive.")
            continue
        return value


def build_grid(bounds, cell_size_meters):
    """Returns (grid, actual_cell_size_meters). Coarsens cell_size_meters if the
    requested size would produce more than MAX_GRID_CELLS cells."""
    grid = bounds.coveringGrid(ee.Projection("EPSG:3857"), cell_size_meters)
    cell_count = grid.size().getInfo()

    if cell_count > MAX_GRID_CELLS:
        # Cell count scales as area / cell_size^2, so scale cell_size by
        # sqrt(cell_count / MAX_GRID_CELLS) to bring it back under the cap.
        adjusted_size = cell_size_meters * math.sqrt(cell_count / MAX_GRID_CELLS)
        print(
            f"{cell_size_meters:.0f}m cells would produce {cell_count} cells over "
            f"this area, above the {MAX_GRID_CELLS}-cell safety cap (Earth Engine's "
            "reduceRegions/getInfo() and the browser both struggle well below "
            f"that). Coarsening to ~{adjusted_size:.0f}m cells instead."
        )
        grid = bounds.coveringGrid(ee.Projection("EPSG:3857"), adjusted_size)
        cell_count = grid.size().getInfo()
        cell_size_meters = adjusted_size

    print(f"Grid: {cell_count} cells at ~{cell_size_meters:.0f}m.")
    return grid, cell_size_meters


def band_value_to_channel(value):
    clamped = max(VIS_MIN, min(VIS_MAX, value))
    return int(round((clamped - VIS_MIN) / (VIS_MAX - VIS_MIN) * 255))


def cell_color(properties, bands):
    values = [properties.get(band) for band in bands]
    if any(v is None for v in values):
        return None
    channels = [band_value_to_channel(v) for v in values]
    if len(channels) == 1:
        channels = channels * 3
    return "#{:02x}{:02x}{:02x}".format(*channels)


def build_map(reduced_geojson, center):
    m = folium.Map(location=center, zoom_start=11)

    for layer_name, bands in LAYERS:
        layer_geojson = {"type": "FeatureCollection", "features": []}
        for feature in reduced_geojson["features"]:
            props = feature["properties"]
            color = cell_color(props, bands)
            popup_lines = [
                f"{band} ({BAND_LABELS[band]}): "
                + ("no data" if props.get(band) is None else f"{props[band]:.0f}")
                for band in BANDS
            ]
            layer_geojson["features"].append(
                {
                    "type": "Feature",
                    "geometry": feature["geometry"],
                    "properties": {
                        "fill_color": color or "#000000",
                        "fill_opacity": 0.0 if color is None else 0.75,
                        "popup_text": "<br>".join(popup_lines),
                    },
                }
            )

        folium.GeoJson(
            layer_geojson,
            name=layer_name,
            style_function=lambda feature: {
                "fillColor": feature["properties"]["fill_color"],
                "color": feature["properties"]["fill_color"],
                "weight": 0,
                "fillOpacity": feature["properties"]["fill_opacity"],
            },
            popup=folium.GeoJsonPopup(fields=["popup_text"], aliases=[""], labels=False),
            show=layer_name == LAYERS[0][0],
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def main():
    bounds_coords, center, display_name, place_name = prompt_place()
    start_date = prompt_date("Start date", "2024-01-01")
    end_date = prompt_date("End date", "2024-12-31")
    max_cloud_percentage = prompt_max_cloud_percentage()
    cell_size_meters = prompt_cell_size_meters()

    authenticate()
    image, image_count = get_city_image(bounds_coords, start_date, end_date, max_cloud_percentage)
    if image_count == 0:
        print(
            "Warning: no Sentinel-2 scenes matched that date range/cloud threshold "
            "for this area - cell values will be empty. Try a wider date range or "
            "a higher max cloud percentage."
        )
    else:
        print(f"Found {image_count} Sentinel-2 scene(s) matching the filters.")

    bounds = ee.Geometry.Rectangle(bounds_coords)
    grid, cell_size_meters = build_grid(bounds, cell_size_meters)

    print("Computing per-cell band means and pulling back GeoJSON...")
    reduced = image.reduceRegions(collection=grid, reducer=ee.Reducer.mean(), scale=10)
    reduced_geojson = reduced.getInfo()

    slug = slugify(place_name)
    geojson_path = os.path.join(os.path.dirname(__file__), f"{slug}_grid.geojson")
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(reduced_geojson, f)
    print(f"Saved raw GeoJSON to {geojson_path}")

    m = build_map(reduced_geojson, center)
    html_path = os.path.join(os.path.dirname(__file__), f"{slug}_grid_map.html")
    m.save(html_path)
    print(f"Saved map to {html_path}")


if __name__ == "__main__":
    main()
