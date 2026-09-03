// Location scoring — pure logic, no Vue. Ported from the realestate-mvp
// Location page. Given a lat/lng, query Overpass (OSM) for nearby POIs and
// derive four 0–100 sub-scores: transport, shopping, health+education, lifestyle.
//
// Kept framework-free so it can be unit-tested on its own (cf. lib/metrics.js).

const OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
const WALK_SPEED_M_PER_MIN = 80 // ~4.8 km/h, used for "X min" labels

// ---- geometry -------------------------------------------------------------
export function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000
  const toRad = (v) => (v * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return Math.round(R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)))
}

function getCoords(el) {
  return { lat: el.lat ?? el.center?.lat, lon: el.lon ?? el.center?.lon }
}

export function walkMinutes(distanceM) {
  return Math.max(1, Math.round(distanceM / WALK_SPEED_M_PER_MIN))
}

// ---- categorisation -------------------------------------------------------
// Returns a stable category key + i18n label key (resolved with $t in the view),
// or null to discard the POI.
export const CATEGORIES = {
  transport: { labelKey: 'location.category.transport', icon: '🚇' },
  shopping: { labelKey: 'location.category.shopping', icon: '🛒' },
  diy: { labelKey: 'location.category.diy', icon: '🧰' },
  education: { labelKey: 'location.category.education', icon: '🏫' },
  healthcare: { labelKey: 'location.category.healthcare', icon: '🏥' },
  fitness: { labelKey: 'location.category.fitness', icon: '🏋️' },
  dining: { labelKey: 'location.category.dining', icon: '🍽' },
}

function categorize(tags) {
  if (tags.shop === 'supermarket') return 'shopping'
  if (tags.shop === 'doityourself' || tags.shop === 'hardware') return 'diy'
  if (tags.highway === 'bus_stop') return 'transport'
  if (tags.amenity === 'school' || tags.amenity === 'kindergarten') return 'education'
  if (tags.amenity === 'hospital' || tags.amenity === 'clinic' || tags.amenity === 'pharmacy' || tags.healthcare)
    return 'healthcare'
  if (tags.leisure === 'fitness_centre') return 'fitness'
  if (['restaurant', 'cafe', 'fast_food'].includes(tags.amenity)) return 'dining'
  return null
}

function getTransportType(tags) {
  const name = (tags.name || '').toLowerCase()
  if (name.includes('метростанция') || name.includes('metro')) return 'metro'
  if (tags.tram === 'yes' || name.includes('трамвай')) return 'tram'
  if (tags.trolleybus === 'yes') return 'trolleybus'
  return 'bus'
}

function distanceScore(distance, maxDistance) {
  if (distance >= maxDistance) return 0
  return Math.round(100 * (1 - distance / maxDistance))
}

// ---- coordinate parsing ---------------------------------------------------
// Accepts "42.69, 23.32" (or whitespace / mixed). Returns {lat,lon} or null.
export function parseCoords(input) {
  const parts = String(input)
    .split(/[,\s]+/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map(Number)
  if (parts.length !== 2 || parts.some((n) => Number.isNaN(n))) return null
  const [lat, lon] = parts
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null
  return { lat, lon }
}

// ---- Overpass fetch -------------------------------------------------------
function buildQuery(lat, lon) {
  return `
  [out:json][timeout:25];
  (
    node["shop"="supermarket"]["name"](around:700, ${lat}, ${lon});
    way["shop"="supermarket"]["name"](around:700, ${lat}, ${lon});
    node["shop"~"doityourself|hardware"]["name"](around:700, ${lat}, ${lon});
    way["shop"~"doityourself|hardware"]["name"](around:700, ${lat}, ${lon});
    node["highway"="bus_stop"]["name"](around:500, ${lat}, ${lon});
    node["amenity"~"school|kindergarten"]["name"](around:1000, ${lat}, ${lon});
    way["amenity"~"school|kindergarten"]["name"](around:1000, ${lat}, ${lon});
    node["amenity"~"hospital|clinic|pharmacy"]["name"](around:1200, ${lat}, ${lon});
    way["amenity"~"hospital|clinic|pharmacy"]["name"](around:1200, ${lat}, ${lon});
    node["leisure"="fitness_centre"]["name"](around:1000, ${lat}, ${lon});
    way["leisure"="fitness_centre"]["name"](around:1000, ${lat}, ${lon});
    node["amenity"~"restaurant|cafe|fast_food"]["name"](around:600, ${lat}, ${lon});
    way["amenity"~"restaurant|cafe|fast_food"]["name"](around:600, ${lat}, ${lon});
  );
  out center tags;
  `
}

// Fetch POIs around a point. Returns a flat array of
// { id, category, name, distance, type } objects.
export async function fetchPois(lat, lon) {
  const res = await fetch(OVERPASS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: buildQuery(lat, lon),
  })
  if (!res.ok) throw new Error(`Overpass returned ${res.status}`)
  const data = await res.json()

  return (data.elements || [])
    .filter((e) => e.tags?.name)
    .map((e) => {
      const coords = getCoords(e)
      if (coords.lat == null || coords.lon == null) return null
      const category = categorize(e.tags)
      if (!category) return null
      return {
        id: e.id,
        category,
        name: e.tags.name,
        distance: haversine(lat, lon, coords.lat, coords.lon),
        type: category === 'transport' ? getTransportType(e.tags) : null,
      }
    })
    .filter(Boolean)
}

// ---- scores ---------------------------------------------------------------
export function transportScore(pois) {
  const transport = pois.filter((p) => p.category === 'transport')
  if (!transport.length) return 0

  const metro = transport.filter((p) => p.type === 'metro')
  const tram = transport.filter((p) => p.type === 'tram')
  const bus = transport.filter((p) => p.type === 'bus' || p.type === 'trolleybus')

  if (metro.length) {
    const d = Math.min(...metro.map((p) => p.distance))
    return Math.min(100, 90 + Math.round((500 - d) / 20))
  }
  if (tram.length) {
    const d = Math.min(...tram.map((p) => p.distance))
    return Math.min(95, 80 + Math.round((500 - d) / 25))
  }
  if (bus.length) {
    const d = Math.min(...bus.map((p) => p.distance))
    return Math.min(80, distanceScore(d, 600))
  }
  return 0
}

export function shoppingScore(pois) {
  const shops = pois.filter((p) => p.category === 'shopping')
  if (!shops.length) return 0
  const best = Math.min(...shops.map((p) => p.distance))
  let score = distanceScore(best, 700)
  if (shops.some((s) => /lidl|kaufland|billa|cba|fantastico/i.test(s.name))) score += 10
  return Math.min(100, score)
}

export function healthEducationScore(pois) {
  const items = pois.filter((p) => p.category === 'education' || p.category === 'healthcare')
  if (!items.length) return 0
  const best = Math.min(...items.map((p) => p.distance))
  return Math.min(100, distanceScore(best, 1200))
}

export function lifestyleScore(pois) {
  const items = pois.filter((p) => p.category === 'dining' || p.category === 'fitness')
  if (!items.length) return 0
  const best = Math.min(...items.map((p) => p.distance))
  return Math.min(100, distanceScore(best, 800))
}

// The four headline metrics, in display order. `labelKey` resolved with $t in the view.
export function scores(pois) {
  return [
    { key: 'transport', icon: '🚇', labelKey: 'location.score.transport', value: transportScore(pois) },
    { key: 'shopping', icon: '🛒', labelKey: 'location.score.shopping', value: shoppingScore(pois) },
    { key: 'health', icon: '🏥', labelKey: 'location.score.health', value: healthEducationScore(pois) },
    { key: 'lifestyle', icon: '🍽', labelKey: 'location.score.lifestyle', value: lifestyleScore(pois) },
  ]
}

// Simple composite — the average of the four sub-scores. Answers "how good
// is this spot overall" at a glance.
export function overallScore(pois) {
  const vals = scores(pois).map((s) => s.value)
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)
}

// Group POIs by category: dedupe by name (keep nearest), sort, top 5 each.
// Returns [{ key, icon, label, items:[{id,name,distance}] }] in CATEGORIES order.
export function groupPois(pois) {
  const nearestByName = new Map()
  for (const p of pois) {
    const k = `${p.category}-${p.name}`
    if (!nearestByName.has(k) || p.distance < nearestByName.get(k).distance) {
      nearestByName.set(k, p)
    }
  }

  const byCat = {}
  for (const p of nearestByName.values()) {
    ;(byCat[p.category] ||= []).push(p)
  }

  return Object.keys(CATEGORIES)
    .filter((key) => byCat[key]?.length)
    .map((key) => ({
      key,
      icon: CATEGORIES[key].icon,
      labelKey: CATEGORIES[key].labelKey,
      items: byCat[key].sort((a, b) => a.distance - b.distance).slice(0, 5),
    }))
}
