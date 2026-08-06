# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Small, standalone scripting project (not a git repo, no build system) for pulling Google Earth
Engine (GEE) satellite/vegetation data over Dehradun, India and rendering it as self-contained
HTML pages (an interactive Leaflet map, and an NDVI history+forecast chart). There is no
application framework or package manifest — each `.py` file is run directly with
`python <file>.py`.

## Files

- `dehradun_gee_map.py` — authenticates to GEE with the service-account key, pulls a
  cloud-filtered Sentinel-2 median composite over a Dehradun bounding box, and writes
  `dehradun_map.html` (a `folium` map with toggleable True Color / False Color NIR / SWIR / and
  individual-band tile layers via `LayerControl`). Also exposes `authenticate()` and
  `DEHRADUN_BOUNDS_COORDS`, imported by `dehradun_ndvi_forecast.py`.
- `dehradun_ndvi_forecast.py` — pulls a multi-year NDVI time series for the same Dehradun ROI
  (regional mean NDVI per Sentinel-2 scene, computed server-side via `reduceRegion` +
  `.getInfo()`), aggregates to monthly medians, fits a numpy-only harmonic regression
  (linear trend + annual/semi-annual sinusoids), forecasts NDVI forward, and writes
  `dehradun_ndvi_forecast.html` (a plotly chart with a 95% interval band). Exposes
  `fetch_ndvi_time_series()`, `monthly_median()`, `fit_harmonic_regression()`, `forecast()`,
  imported by `dehradun_ndvi_timeline_map.py` rather than duplicated.
- `dehradun_ndvi_timeline_map.py` — puts the same observed+forecast NDVI series on the actual
  Dehradun map instead of a chart: one ROI polygon per month, colored by NDVI on a brown→green
  `branca` colormap, scrubbed with folium's `TimestampedGeoJson` time slider (observed months vs.
  forecast months both included, distinguished in the popup text). A Sentinel-2 True Color layer
  from `dehradun_gee_map.get_dehradun_image()`/`add_ee_layer()` sits underneath for spatial
  context. Writes `dehradun_ndvi_timeline_map.html`. Note this colors the *whole* ROI a single
  flat color per month (the regional-average NDVI, not a real per-pixel map) — consistent with the
  single-regional-average scope decision below.
- `gee_city_map.py` — interactive, place/time-agnostic version of `dehradun_gee_map.py`. Prompts
  the user for a place name, a start/end date, and a max cloud-cover percentage; geocodes the place
  via the OpenStreetMap Nominatim API (`urllib.request` only — no new dependency, so no DLL-blocking
  risk) to get a bounding box + center, then reuses `authenticate()`, `BANDS`, `BAND_LABELS`, and
  `add_ee_layer()` from `dehradun_gee_map.py` to build the same True Color / False Color NIR / SWIR
  / individual-band layer set over that place/time. Writes `<slugified place name>_map.html`.
  Nominatim requires a descriptive `User-Agent` (set in `USER_AGENT`) and needs live internet access
  at runtime — if geocoding fails, check connectivity before assuming a code bug.
- `get_started_with_earth_engine_for_python.py` — a Colab-exported EE quickstart/tutorial script
  (uses `geemap`/`ipyleaflet`/`altair`, interactive `ee.Authenticate()` flow). Reference only, not
  wired into the main scripts.
- `gisproject-503012-b7a893527fcb.json` — **live GCP service-account key** (project
  `gisproject-503012`, account `anurag@gisproject-503012.iam.gserviceaccount.com`). This is a real
  credential checked into the working directory, not a placeholder — treat its contents as a
  secret (don't print it, upload it, or copy it into other files/commits).

## Running

```powershell
python dehradun_gee_map.py            # -> dehradun_map.html
python dehradun_ndvi_forecast.py      # -> dehradun_ndvi_forecast.html
python dehradun_ndvi_timeline_map.py  # -> dehradun_ndvi_timeline_map.html
python gee_city_map.py                # -> interactive prompts; <place>_map.html
```

All outputs are self-contained HTML written next to the script; open directly in a browser (no
local server needed). Required packages: `earthengine-api`, `folium`, `numpy`, `plotly` (install
with `python -m pip install earthengine-api folium numpy plotly`; `branca` comes in as a `folium`
dependency and is used directly for the NDVI colormap). Deliberately NOT used: `pandas`,
`prophet`, `geemap` — see the DLL-blocking note below before adding either back.

There is no lint/test/build tooling in this repo.

## Architecture notes specific to this codebase

- **Auth is service-account only, not `ee.Authenticate()`.** `dehradun_gee_map.py` builds
  `ee.ServiceAccountCredentials(SERVICE_ACCOUNT, KEY_FILE)` and calls
  `ee.Initialize(credentials, project=PROJECT_ID)` — this must run before any `ee.Geometry`/
  `ee.ImageCollection` object is constructed, since those calls hit the EE API on init. Keep
  geometry/image construction inside functions called after `authenticate()`, not at module scope.
- **Freshly pip-installed compiled packages get their DLLs blocked on this machine** by a Windows
  Application Control policy (`ImportError: DLL load failed ... An Application Control policy has
  blocked this file`). Confirmed blocked: `python-box` (a `geemap` dependency) and, separately,
  `pandas` itself (any version — there's also no prebuilt `pandas` wheel for the installed Python
  3.14, so downgrading isn't an option either). Confirmed working: `numpy`, `earthengine-api`,
  `folium`, `plotly.graph_objects`. The pattern seems to be "newly downloaded/unrecognized binary"
  rather than anything specific to those packages, so treat any *new* compiled dependency as a risk
  — sanity-check with a bare `python -c "import <pkg>"` before building on it, and prefer
  numpy/stdlib-only approaches (as `dehradun_ndvi_forecast.py` does) over pandas- or
  Prophet-based ones. `geemap` is avoided for the same reason: the current map script talks to `ee`
  and `folium` directly instead — `image.getMapId(vis_params)` returns a tile URL fetcher, wrapped
  manually in `folium.TileLayer(...)` (see `add_ee_layer()` in `dehradun_gee_map.py`).
- **GCP IAM is a common failure point, not a code bug.** `ee.Initialize(...)` can fail with
  `403 ... USER_PROJECT_DENIED` / "Grant the caller the roles/serviceusage.serviceUsageConsumer
  role" even when the code is correct. Fix in Google Cloud Console (IAM & Admin) by granting the
  service account `roles/serviceusage.serviceUsageConsumer` and an Earth Engine role (e.g.
  `roles/earthengine.viewer`), confirming the Earth Engine API is enabled for the project, and
  confirming the project is registered for Earth Engine at
  https://code.earthengine.google.com/register. This is not something to work around in code.
- **Data source and bands**: `COPERNICUS/S2_SR_HARMONIZED`, filtered to a Dehradun bounding box
  (`DEHRADUN_BOUNDS_COORDS`) and `CLOUDY_PIXEL_PERCENTAGE < 20`, reduced with `.median()` over
  BANDS = `['B2','B3','B4','B8','B11','B12']` (Blue/Green/Red/NIR/SWIR1/SWIR2). Map layers are
  built from combinations of these six bands (`build_map()` / `add_ee_layer()`). Native resolution
  is 10 m for B2/B3/B4/B8 and 20 m for B11/B12 — the rendered map tiles are resampled to whatever
  zoom level the browser requests, so on-screen sharpness is a display artifact, not the true
  resolution.
- **NDVI forecast scope is a single regional average, not per-pixel.** `dehradun_ndvi_forecast.py`
  reduces NDVI to one scalar per Sentinel-2 scene over the whole ROI (`reduceRegion(mean)`), not a
  spatial forecast map — this was a deliberate scope choice (fast, one lightweight model, easy to
  sanity check) over a per-grid-cell forecast (many models, heavier, harder to validate). Keep this
  in mind if asked to extend it to a spatial forecast.
