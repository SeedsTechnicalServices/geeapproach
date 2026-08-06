"""Forecast vegetation (NDVI) for Dehradun using Google Earth Engine data.

Pipeline:
  1. Pull a historical NDVI time series for the Dehradun ROI from Sentinel-2
     (regional mean NDVI per image date, computed server-side in Earth Engine).
  2. Aggregate to one median NDVI value per month (smooths residual cloud noise).
  3. Fit a harmonic regression (linear trend + annual/semi-annual sinusoids) with
     numpy least squares - a lightweight, classical model for seasonal vegetation
     indices that needs no training framework.
  4. Forecast NDVI forward and render history + forecast as an interactive HTML
     chart (plotly).

Note: pandas and prophet are NOT used here. On this machine, freshly-installed
compiled packages (pandas, geemap's `box` dependency) get their DLLs blocked by
a Windows Application Control policy - see CLAUDE.md. numpy, earthengine-api,
folium and plotly's graph_objects module were confirmed to work, so this script
sticks to those.
"""

import os
from datetime import date, datetime, timedelta

import numpy as np
import plotly.graph_objects as go

from dehradun_gee_map import authenticate, DEHRADUN_BOUNDS_COORDS

import ee

START_DATE = "2019-01-01"
END_DATE = date.today().isoformat()
CLOUDY_PIXEL_PERCENTAGE_MAX = 50
REDUCE_SCALE_METERS = 30
FORECAST_MONTHS = 12
HARMONICS = 2  # annual + semi-annual cycle
OUTPUT_HTML = os.path.join(os.path.dirname(__file__), "dehradun_ndvi_forecast.html")


def fetch_ndvi_time_series():
    bounds = ee.Geometry.Rectangle(DEHRADUN_BOUNDS_COORDS)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(bounds)
        .filterDate(START_DATE, END_DATE)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUDY_PIXEL_PERCENTAGE_MAX))
    )

    def to_feature(image):
        ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
        stats = ndvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=bounds,
            scale=REDUCE_SCALE_METERS,
            bestEffort=True,
        )
        return ee.Feature(None, {
            "date": image.date().format("YYYY-MM-dd"),
            "ndvi": stats.get("NDVI"),
        })

    features = collection.map(to_feature).filter(ee.Filter.notNull(["ndvi"]))
    result = features.getInfo()  # plain GeoJSON dict - no pandas involved

    records = []
    for f in result["features"]:
        props = f["properties"]
        records.append((datetime.strptime(props["date"], "%Y-%m-%d"), props["ndvi"]))
    records.sort(key=lambda r: r[0])
    return records


def monthly_median(records):
    buckets = {}
    for dt, ndvi in records:
        key = (dt.year, dt.month)
        buckets.setdefault(key, []).append(ndvi)

    months = sorted(buckets)
    dates = [date(year, month, 15) for year, month in months]
    values = [float(np.median(buckets[key])) for key in months]
    return dates, values


def design_matrix(t_years):
    cols = [np.ones_like(t_years), t_years]
    for k in range(1, HARMONICS + 1):
        cols.append(np.sin(2 * np.pi * k * t_years))
        cols.append(np.cos(2 * np.pi * k * t_years))
    return np.column_stack(cols)


def fit_harmonic_regression(dates, values):
    t_days = np.array([(d - dates[0]).days for d in dates], dtype=float)
    t_years = t_days / 365.25
    y = np.array(values, dtype=float)

    X = design_matrix(t_years)
    coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ coeffs
    residual_std = float(np.std(y - fitted, ddof=X.shape[1]))

    trend_per_year = coeffs[1]
    return coeffs, fitted, residual_std, trend_per_year, dates[0]


def forecast(coeffs, residual_std, anchor_date, last_t_days, months=FORECAST_MONTHS):
    future_t_days = last_t_days + np.arange(1, months + 1) * 30.44
    future_t_years = future_t_days / 365.25
    X_future = design_matrix(future_t_years)
    y_future = X_future @ coeffs

    future_dates = [anchor_date + timedelta(days=float(d)) for d in future_t_days]
    lower = y_future - 1.96 * residual_std
    upper = y_future + 1.96 * residual_std
    return future_dates, y_future, lower, upper


def build_chart(hist_dates, hist_values, fitted, future_dates, future_values, lower, upper, trend_per_year):
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=hist_dates, y=hist_values, mode="markers", name="Observed NDVI (monthly median)",
        marker=dict(size=6, color="#2c7a3d"),
    ))
    fig.add_trace(go.Scatter(
        x=hist_dates, y=fitted, mode="lines", name="Fitted (harmonic regression)",
        line=dict(color="#2c7a3d", width=1, dash="dot"),
    ))
    fig.add_trace(go.Scatter(
        x=future_dates, y=future_values, mode="lines+markers", name="Forecast",
        line=dict(color="#d97706", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=future_dates + future_dates[::-1],
        y=list(upper) + list(lower[::-1]),
        fill="toself", fillcolor="rgba(217,119,6,0.15)",
        line=dict(color="rgba(0,0,0,0)"), hoverinfo="skip",
        name="95% interval",
    ))

    trend_note = "greening" if trend_per_year > 0 else "browning"
    fig.update_layout(
        title=(
            f"Dehradun NDVI: history + {FORECAST_MONTHS}-month forecast "
            f"(trend: {trend_per_year:+.4f} NDVI/yr, {trend_note})"
        ),
        xaxis_title="Date",
        yaxis_title="NDVI",
        template="plotly_white",
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def main():
    authenticate()
    records = fetch_ndvi_time_series()
    if len(records) < 12:
        raise RuntimeError(f"Only {len(records)} usable NDVI observations found - need more history to forecast.")

    dates, values = monthly_median(records)
    coeffs, fitted, residual_std, trend_per_year, anchor_date = fit_harmonic_regression(dates, values)

    last_t_days = (dates[-1] - anchor_date).days
    future_dates, future_values, lower, upper = forecast(coeffs, residual_std, anchor_date, last_t_days)

    fig = build_chart(dates, values, fitted, future_dates, future_values, lower, upper, trend_per_year)
    fig.write_html(OUTPUT_HTML)
    print(f"Used {len(records)} scenes -> {len(dates)} monthly points.")
    print(f"Trend: {trend_per_year:+.5f} NDVI/year. Saved forecast chart to {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
