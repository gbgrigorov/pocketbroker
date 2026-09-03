# Real-Time Air Quality on the Location Analyzer (Lazy Load)

> **Status:** Build instructions — not yet implemented. Run when ready.
> **Goal:** When a user pastes coordinates into the Location Score tool (`/location`) and analyses a spot, lazily fetch the *current* air quality for those coordinates and show it as one more score card — without blocking the existing POI analysis.

## Why this design

AQICN's free API has **no usable history** (confirmed by probing: the feed gives a live reading plus a ~1-week forecast window, nothing per-year). But it is *excellent* for "what's the air like at this spot right now," because of its **geo feed** endpoint:

```
GET https://api.waqi.info/feed/geo:{lat};{lon}/?token={AQICN_TOKEN}
```

It returns the nearest station's live AQI + available pollutants. Verified for Sofia:

| Coordinate | Nearest station | AQI | PM10 | NO2 |
|---|---|---|---|---|
| 42.6597, 23.3250 (Лозенец) | Hipodruma | 12 | 12 | 5.1 |
| 42.7300, 23.3000 (Надежда) | Nadezhda | 18 | 15 | 3.9 |
| 42.6550, 23.3780 (Младост) | Mladost | 17 | 17 | 1.7 |

Note: official Sofia stations report **AQI + PM10 + NO2 + O3**; PM2.5 (`iaqi.pm25`) is often **null** at official stations (present at citizen sensors). So the UI must render whatever pollutants are present and always fall back to the overall AQI.

This pairs naturally with `LocationView.vue`, which already takes pasted coordinates and lazily fetches POIs from Overpass — we add one more lazy fetch alongside it.

## Security constraint (do not skip)

**The AQICN token must never reach the browser.** Call AQICN **server-side** from a FastAPI endpoint; the frontend calls our own `/api/...`, never `api.waqi.info` directly. Put the token in `.env` as `AQICN_TOKEN` (server-side only).

---

## Step 1 — Backend endpoint

**File:** `backend/app/routes.py`

Add a coordinate-based current-air endpoint. It calls the AQICN geo feed server-side, normalises the response, and caches briefly (air doesn't change minute-to-minute; a short TTL protects the free-tier rate limit).

```python
import time
import httpx

# module-level tiny TTL cache: (lat_round, lon_round) -> (expires_at, payload)
_air_now_cache: dict[tuple, tuple[float, dict]] = {}
_AIR_NOW_TTL = 1800  # 30 min


@router.get("/air/current")
def air_current(lat: float, lon: float):
    """Current air quality at a coordinate via the nearest AQICN station.

    Server-side proxy so the AQICN token never reaches the browser. Cached
    per ~rounded coordinate for 30 min. Returns None-ish fields when AQICN has
    no nearby station or the token is unset.
    """
    token = os.environ.get("AQICN_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="air quality not configured")

    key = (round(lat, 3), round(lon, 3))
    hit = _air_now_cache.get(key)
    now = time.time()
    if hit and hit[0] > now:
        return hit[1]

    url = f"https://api.waqi.info/feed/geo:{lat};{lon}/?token={token}"
    try:
        r = httpx.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail="air quality upstream error")

    if data.get("status") != "ok":
        payload = {"available": False}
    else:
        d = data["data"]
        iaqi = d.get("iaqi", {})
        def _v(k):
            return iaqi.get(k, {}).get("v")
        payload = {
            "available": True,
            "aqi": d.get("aqi"),
            "station": d.get("city", {}).get("name"),
            "time": d.get("time", {}).get("s"),
            "pm25": _v("pm25"),
            "pm10": _v("pm10"),
            "no2": _v("no2"),
            "o3": _v("o3"),
            "dominant": d.get("dominentpol"),  # AQICN's spelling
        }

    _air_now_cache[key] = (now + _AIR_NOW_TTL, payload)
    return payload
```

Notes:
- `httpx` is already a backend dependency (used by the test client).
- Reuse the existing `os` and `HTTPException` imports already at the top of `routes.py`.
- This endpoint is public (no auth) — it exposes only public environmental data, no gated builder/owner info.

**Test** (`backend/tests/test_air_current.py`) — mock httpx so no live call in CI:

```python
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

_FAKE = {"status": "ok", "data": {
    "aqi": 17, "city": {"name": "Mladost, Sofia"},
    "time": {"s": "2026-06-17 20:00:00"},
    "iaqi": {"pm10": {"v": 17}, "no2": {"v": 1.7}},
    "dominentpol": "pm10",
}}

def test_air_current_normalises(monkeypatch):
    monkeypatch.setenv("AQICN_TOKEN", "x")
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return _FAKE
    with patch("app.routes.httpx.get", return_value=_Resp()):
        body = TestClient(app).get("/api/air/current?lat=42.655&lon=23.378").json()
    assert body["available"] is True
    assert body["aqi"] == 17
    assert body["pm10"] == 17
    assert body["pm25"] is None  # official station, no pm25
```

---

## Step 2 — Frontend API wrapper

**File:** `frontend/src/api/index.js` — add to the exported `api` object:

```js
airCurrent: (lat, lon) => get(`/air/current?lat=${lat}&lon=${lon}`),
```

---

## Step 3 — Lazy load in the Location analyzer

**File:** `frontend/src/views/LocationView.vue`

The view already parses coordinates and runs an analysis on demand. Add a *separate, non-blocking* air fetch so a slow/failed AQICN call never holds up the POI scores.

In `<script setup>`:

```js
import { api } from '../api'

const air = ref(null)        // null = not loaded; { available, aqi, ... }
const airLoading = ref(false)

async function loadAir(lat, lon) {
  airLoading.value = true
  air.value = null
  try {
    air.value = await api.airCurrent(lat, lon)
  } catch {
    air.value = { available: false }
  } finally {
    airLoading.value = false
  }
}
```

Call `loadAir(lat, lon)` from the same handler that runs the POI analysis, right after `parseCoords` yields a valid lat/lon — but do **not** `await` it in series with the POI fetch; fire it alongside so both load in parallel (true lazy/independent load).

AQI colour helper (matches the map metric thresholds):

```js
function aqiColor(v) {
  if (v == null) return 'var(--neutral)'
  if (v <= 50) return '#22c55e'
  if (v <= 100) return '#eab308'
  if (v <= 150) return '#f97316'
  return '#ef4444'
}
```

Template — an air card near the score cards:

```vue
<div v-if="airLoading" class="air-card mono">Loading air quality…</div>
<div v-else-if="air && air.available" class="air-card" :style="{ borderColor: aqiColor(air.aqi) }">
  <div class="air-card__aqi" :style="{ color: aqiColor(air.aqi) }">AQI {{ air.aqi }}</div>
  <div class="air-card__detail mono">
    <span v-if="air.pm25 != null">PM2.5 {{ air.pm25 }}</span>
    <span v-if="air.pm10 != null">PM10 {{ air.pm10 }}</span>
    <span v-if="air.no2 != null">NO₂ {{ air.no2 }}</span>
  </div>
  <div class="air-card__src mono">{{ air.station }} · {{ air.time }}</div>
</div>
<div v-else-if="air" class="air-card mono">No nearby air station.</div>
```

Add i18n keys (`en.js` + `bg.js`, key parity) under a `location.air.*` namespace for the labels above instead of the hard-coded English shown here.

---

## Verification

1. `AQICN_TOKEN` in `backend/.env` (server-side).
2. Backend test: `cd backend && .venv/bin/python -m pytest tests/test_air_current.py -q` → passes (mocked).
3. Live smoke: `curl "http://localhost:8000/api/air/current?lat=42.6597&lon=23.3250"` → JSON with `aqi` + `station: "Hipodruma…"`.
4. Open `/location`, paste `42.6597, 23.3250`, analyse → POI scores appear immediately; the air card fills in independently a moment later.
5. Second analyse of a nearby spot within 30 min → served from cache (no new upstream call).

## Out of scope (handled separately)

Historical year-over-year air quality is **not** this feature — AQICN has no history. That comes from the Sensor.Community citizen-sensor archive feeding the map's year slider — see `HISTORICAL_SENSORCOMMUNITY.md`.
```
