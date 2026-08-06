"""Put the Dehradun NDVI history + forecast on the actual map, with a time
slider: one colored Dehradun-ROI region per month (observed NDVI for past
months, forecast NDVI for future months), scrubbed via folium's
TimestampedGeoJson control. A True Color Sentinel-2 composite sits underneath
for spatial context.

Reuses the GEE auth/ROI helpers from dehradun_gee_map.py and the NDVI
fetch/fit/forecast pipeline from dehradun_ndvi_forecast.py rather than
duplicating them.
"""

import os

import folium
from folium.plugins import TimestampedGeoJson
from branca.colormap import LinearColormap

from dehradun_gee_map import authenticate, DEHRADUN_BOUNDS_COORDS, DEHRADUN_CENTER, get_dehradun_image, add_ee_layer
from dehradun_ndvi_forecast import fetch_ndvi_time_series, monthly_median, fit_harmonic_regression, forecast as forecast_ndvi

OUTPUT_HTML = os.path.join(os.path.dirname(__file__), "dehradun_ndvi_timeline_map.html")

NDVI_COLORMAP = LinearColormap(
    colors=["#8B5A2B", "#D9C36A", "#A8D08D", "#4F9D3D", "#1B5E20"],
    vmin=0.0,
    vmax=0.8,
)


def rectangle_ring(bounds_coords):
    min_lon, min_lat, max_lon, max_lat = bounds_coords
    return [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]


def build_features(dates, values, forecast_flags):
    ring = rectangle_ring(DEHRADUN_BOUNDS_COORDS)
    features = []
    for dt, value, is_forecast in zip(dates, values, forecast_flags):
        clamped = max(0.0, min(0.8, value))
        color = NDVI_COLORMAP(clamped)
        label = "Forecast" if is_forecast else "Observed"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "times": [dt.isoformat()],
                "style": {
                    "fillColor": color,
                    "color": "#333333",
                    "weight": 1,
                    "fillOpacity": 0.55,
                },
                "popup": f"{dt.strftime('%b %Y')} - NDVI {value:.3f} ({label})",
            },
        })
    return features


def main():
    authenticate()

    records = fetch_ndvi_time_series()
    dates, values = monthly_median(records)
    coeffs, fitted, residual_std, trend_per_year, anchor_date = fit_harmonic_regression(dates, values)

    last_t_days = (dates[-1] - anchor_date).days
    future_dates, future_values, _, _ = forecast_ndvi(coeffs, residual_std, anchor_date, last_t_days)

    all_dates = dates + future_dates
    all_values = list(values) + list(future_values)
    forecast_flags = [False] * len(dates) + [True] * len(future_dates)
    features = build_features(all_dates, all_values, forecast_flags)

    m = folium.Map(location=DEHRADUN_CENTER, zoom_start=11, tiles="CartoDB positron")

    reference_image = get_dehradun_image()
    add_ee_layer(
        m, reference_image, {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000},
        "Sentinel-2 True Color (reference)",
    )

    TimestampedGeoJson(
        {"type": "FeatureCollection", "features": features},
        period="P1M",
        duration="P1M",
        transition_time=300,
        auto_play=False,
        loop=False,
        add_last_point=False,
        date_options="YYYY-MM",
        time_slider_drag_update=True,
    ).add_to(m)

    NDVI_COLORMAP.caption = "NDVI (Dehradun regional monthly average)"
    NDVI_COLORMAP.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    m.save(OUTPUT_HTML)
    print(f"{len(dates)} observed months + {len(future_dates)} forecast months -> {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
