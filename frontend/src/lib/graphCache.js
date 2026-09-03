/* sessionStorage cache for the global ownership graph (/api/graph).
 *
 * The payload is ~1MB and identical for every signed-in viewer, but the entity
 * browse page refetched it on every visit — a refresh cost a full round-trip
 * before the constellation could draw. sessionStorage (not localStorage) is the
 * right scope: it survives a refresh, dies with the tab, and never leaks the
 * people graph onto disk for the next person at the machine.
 *
 * Three things this guards against:
 *   - staleness — entries expire (TTL), so an ETL/deploy can't be papered over
 *     for longer than that; the server cache is invalidated on restart anyway.
 *   - quota     — a ~1MB write can throw QuotaExceededError. That is not an
 *     error worth surfacing: we just skip caching and behave exactly as before.
 *   - identity  — the graph is login-gated, so any token change (login, logout,
 *     token rejected) must drop it. authStore.setToken calls clearGraphCache().
 */

const KEY = 'pb:graph:v1' // bump the suffix if the payload shape changes
const POS_KEY = 'pb:graphpos:v1' // settled node coordinates for the same payload
const TTL_MS = 30 * 60 * 1000 // 30 min

export function readGraph(limit) {
  let raw
  try {
    raw = sessionStorage.getItem(KEY)
  } catch {
    return null // storage disabled (private mode / blocked cookies)
  }
  if (!raw) return null
  try {
    const { limit: l, ts, payload } = JSON.parse(raw)
    if (l !== limit || !payload) return null
    if (!Number.isFinite(ts) || Date.now() - ts > TTL_MS) {
      clearGraphCache()
      return null
    }
    return payload
  } catch {
    clearGraphCache() // corrupt entry — drop it rather than fail the view
    return null
  }
}

export function writeGraph(limit, payload) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ limit, ts: Date.now(), payload }))
  } catch {
    /* over quota or storage disabled — caching is an optimisation, not a
       requirement; the view still works, it just refetches next time. */
  }
}

/* Settled layout coordinates, cached separately from the payload.
 *
 * Caching the payload only removed the fetch (~300ms). The dominant cost on
 * this page is the force-directed pre-settle: 2000 nodes x 400 ticks blocks the
 * main thread for ~8s, and it ran on every page load because the component's
 * position map is in-memory and starts empty. Restoring coordinates means the
 * graph is already settled and needs no ticks at all.
 *
 * Stored apart from the payload so a quota failure on one doesn't lose the
 * other, and so stale coordinates are always harmless: they are only seeds, and
 * any node without one simply starts where the simulation would have put it.
 */
export function readLayout(key) {
  let raw
  try {
    raw = sessionStorage.getItem(POS_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const { key: k, ts, pos } = JSON.parse(raw)
    if (k !== key || !pos) return null
    if (!Number.isFinite(ts) || Date.now() - ts > TTL_MS) {
      clearLayout()
      return null
    }
    return pos
  } catch {
    clearLayout()
    return null
  }
}

export function writeLayout(key, pos) {
  // Round to whole pixels: these are screen coordinates, and full float
  // precision roughly doubles the serialised size for no visible difference.
  const rounded = {}
  for (const id in pos) {
    const p = pos[id]
    if (Number.isFinite(p?.x) && Number.isFinite(p?.y)) {
      rounded[id] = { x: Math.round(p.x), y: Math.round(p.y) }
    }
  }
  try {
    sessionStorage.setItem(POS_KEY, JSON.stringify({ key, ts: Date.now(), pos: rounded }))
  } catch {
    /* over quota or storage disabled — the next load just re-settles. */
  }
}

export function clearLayout() {
  try {
    sessionStorage.removeItem(POS_KEY)
  } catch {
    /* nothing to do */
  }
}

export function clearGraphCache() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* nothing to do */
  }
  clearLayout()
}
