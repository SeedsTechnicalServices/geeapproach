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

### Keys / credentials

| Key | Used by | Required? |
| --- | --- | --- |
| GCP service-account key JSON | All scripts (via `authenticate()` in `dehradun_gee_map.py`) | Yes |
| Nominatim `User-Agent` string | `gee_city_map.py`, `gee_city_grid_map.py` | No signup — just a descriptive string, already set in `USER_AGENT` |

The only real credential in this project is the **GCP service-account key** used to authenticate
to Earth Engine (the scripts use `ee.ServiceAccountCredentials(...)`, not the interactive
`ee.Authenticate()` flow). There are no other API keys — place lookups go through the
OpenStreetMap Nominatim API, which doesn't require a key, only a descriptive `User-Agent` header
(already set via `USER_AGENT` in `gee_city_map.py`).

#### How to procure the GCP service-account key

1. Create or pick a GCP project (https://console.cloud.google.com/).
2. Register that project for Earth Engine: https://code.earthengine.google.com/register (choose
   the non-commercial or commercial track as applicable).
3. Enable the **Earth Engine API** for the project (APIs & Services → Library).
4. Create a service account: IAM & Admin → Service Accounts → Create Service Account.
5. Grant the service account two roles:
   - `roles/serviceusage.serviceUsageConsumer`
   - An Earth Engine role, e.g. `roles/earthengine.viewer` (use `roles/earthengine.writer` if a
     script needs to write EE assets, which none currently do).
6. On that service account, go to **Keys → Add Key → Create new key → JSON** and download it —
   this is the credential file the scripts load.
7. Save the downloaded JSON in the project root and point `dehradun_gee_map.py` at it:
   - `SERVICE_ACCOUNT` — the service account's email (`...@<project-id>.iam.gserviceaccount.com`)
   - `KEY_FILE` — the JSON file's name
   - `PROJECT_ID` — the GCP project ID

**Never commit the key file.** It's covered by `.gitignore` already — keep it that way, and treat
its contents as a secret (don't print it, paste it into chat/issues, or upload it anywhere).

## Running

```powershell
python dehradun_gee_map.py            # -> dehradun_map.html
python dehradun_ndvi_forecast.py      # -> dehradun_ndvi_forecast.html
python dehradun_ndvi_timeline_map.py  # -> dehradun_ndvi_timeline_map.html
python gee_city_map.py                # -> interactive prompts; <place>_map.html
python gee_city_grid_map.py           # -> interactive prompts; <place>_grid.geojson + <place>_grid_map.html
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
| `gee_city_grid_map.py` | Vector/GeoJSON variant of `gee_city_map.py` — reduces the composite to a grid of cells (`ee.Geometry.coveringGrid` + `reduceRegions`) with per-cell band means, writes both the raw `<place>_grid.geojson` and a colored-cell Leaflet map. Auto-coarsens the grid if the requested cell size would exceed a 2000-cell safety cap. |
| `get_started_with_earth_engine_for_python.py` | Reference-only Colab-exported EE quickstart (not wired into the main scripts). |

See `CLAUDE.md` for detailed architecture notes, data sources/bands, and known failure modes
(IAM permission errors, DLL blocking, etc.).

## Security note

A live GCP service-account key (`gisproject-503012-b7a893527fcb.json`) exists in the working
directory for local development. It has been verified **never committed** to this repo's git
history (checked across all branches) and is excluded via `.gitignore` — keep it that way. If it
is ever committed or otherwise leaked, treat it as compromised and rotate/revoke it immediately in
GCP IAM (Service Accounts → Keys → Delete, then issue a new key).
