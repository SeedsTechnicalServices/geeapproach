# geeapproach

Standalone scripts for pulling Google Earth Engine (GEE) satellite/vegetation data and
rendering it as self-contained HTML pages: interactive Leaflet maps and an NDVI history +
forecast chart. Originally built for Dehradun, India; `gee_city_map.py` generalizes the map to
any place name.

No build system, no package manifest — each `.py` file is run directly.

## Setup

```powershell
python -m pip install earthengine-api folium numpy plotly
```

`branca` comes in as a `folium` dependency and is used directly for the NDVI colormap.

Deliberately **not** used: `pandas`, `prophet`, `geemap`. On this project's original dev
machine, freshly pip-installed compiled packages (including `python-box` and `pandas`) got
blocked by a Windows Application Control policy. If you hit
`ImportError: DLL load failed ... An Application Control policy has blocked this file`, sanity
check any new compiled dependency with `python -c "import <pkg>"` before building on it, and
prefer numpy/stdlib-only approaches.

### Credentials

The scripts authenticate to Earth Engine with a GCP service-account key file, not
`ee.Authenticate()`. You need:

- A GCP project registered for Earth Engine (https://code.earthengine.google.com/register).
- A service-account key JSON with `roles/serviceusage.serviceUsageConsumer` and an Earth Engine
  role (e.g. `roles/earthengine.viewer`) granted, and the Earth Engine API enabled.
- The key file path/account and project ID wired into `authenticate()` in `dehradun_gee_map.py`.

**Never commit the key file.** Keep it out of version control (see `.gitignore`) and treat its
contents as a secret.

## Running

```powershell
python dehradun_gee_map.py            # -> dehradun_map.html
python dehradun_ndvi_forecast.py      # -> dehradun_ndvi_forecast.html
python dehradun_ndvi_timeline_map.py  # -> dehradun_ndvi_timeline_map.html
python gee_city_map.py                # -> interactive prompts; <place>_map.html
```

All outputs are self-contained HTML written next to the script; open directly in a browser, no
local server needed.

## Files

| File | Purpose |
| --- | --- |
| `dehradun_gee_map.py` | Sentinel-2 cloud-filtered median composite over Dehradun as a toggleable-layer Leaflet map. |
| `dehradun_ndvi_forecast.py` | Multi-year regional-average NDVI time series + numpy-only harmonic regression forecast, as a Plotly chart. |
| `dehradun_ndvi_timeline_map.py` | Same observed+forecast NDVI series as a time-sliderable choropleth on the map instead of a chart. |
| `gee_city_map.py` | Place/time-agnostic version of `dehradun_gee_map.py` — geocodes any place name via Nominatim. |
| `gee_city_grid_map.py` | Grid-based variant of the city map. |
| `get_started_with_earth_engine_for_python.py` | Reference-only Colab-exported EE quickstart (not wired into the main scripts). |

See `CLAUDE.md` for detailed architecture notes, data sources/bands, and known failure modes
(IAM permission errors, DLL blocking, etc.).

## Security note

This repo has previously had a live GCP service-account key committed to it
(`gisproject-503012-b7a893527fcb.json`). If that key is still present in git history, treat it as
compromised: rotate/revoke it in GCP IAM regardless of whether the repo is public or private.
