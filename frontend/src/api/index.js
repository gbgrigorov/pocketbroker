// Fetch wrappers for the FastAPI backend (proxied at /api in dev).

// Auth token lives in localStorage (written by stores/authStore). Read it here
// directly to avoid an api ⇄ store import cycle.
export const TOKEN_KEY = 'bg_token'
function authHeaders() {
  const t = localStorage.getItem(TOKEN_KEY)
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function get(path) {
  const res = await fetch(`/api${path}`, { headers: { ...authHeaders() } })
  if (res.status === 401) localStorage.removeItem(TOKEN_KEY) // stale/expired token
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

// POST JSON by default, or form-urlencoded when { form: true } (fastapi-users login).
async function post(path, body, { form = false } = {}) {
  const headers = { ...authHeaders() }
  let payload
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = new URLSearchParams(body).toString()
  } else {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method: 'POST', headers, body: payload })
  if (!res.ok) {
    let detail = `${path} → ${res.status}`
    try { detail = (await res.json()).detail || detail } catch { /* non-JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json()
}

// Build a `?a=b&c=d` query string from the truthy entries of an object.
function qs(params) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') p.set(k, v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  // [{ slug, name, lat, lon, neighbourhood_count, avg_eur_sqm }]
  cities: () => get('/cities'),
  // [{ slug, name, lat, lon, latest:{sale,rent}, by_year:{ "2025":{sale,rent}, … } }]
  // All years travel together — fetched once per city; the slider filters locally.
  map: (city) => get(`/map${qs({ city })}`),
  // { slug, name, district, lat, lon }
  neighbourhood: (slug, city) => get(`/neighbourhoods/${slug}${qs({ city })}`),
  // { slug, name, transaction_type, series:[{period_date,price_eur_sqm}], by_type:{...} }
  prices: (slug, txn = 'sale', city) =>
    get(`/neighbourhoods/${slug}/prices${qs({ transaction_type: txn, city })}`),
  // [{ slug, name, direction, distance_m, lat, lon, series:[{period_date,price_eur_sqm}] }]
  neighbours: (slug, city) => get(`/neighbourhoods/${slug}/neighbours${qs({ city })}`),
  // [{ period_date, price_eur_per_gram }]
  gold: () => get('/reference/gold'),
  // [{ year, amount_eur, amount_bgn }]
  minWage: () => get('/reference/min-wage'),

  // --- Phase 3 / 3.5: builders + ownership graph ---------------------------
  // { data_scanned_mb, data_points, builders, projects, sites, scopes, last_run }
  stats: () => get('/stats'),
  // bounded global graph: { nodes:[…], edges:[…], truncated }
  graph: (limit = 800) => get(`/graph?limit=${limit}`),

  // Entity-wide browse (any company/builder/person, not just licensed builders).
  // { total, items:[{ id, eik, person_key, key, kind, name, is_builder, status, degree }] }
  entities: (q, kind, { hasSignals = false, limit = 50, offset = 0 } = {}) => {
    const p = new URLSearchParams()
    if (q) p.set('q', q)
    if (kind && kind !== 'all') p.set('kind', kind)
    if (hasSignals) p.set('has_signals', 'true')
    p.set('limit', String(limit))
    p.set('offset', String(offset))
    return get(`/entities?${p.toString()}`)
  },
  // "Order a research" lead capture (shown when a search returns no matches).
  // challenge: { question:"9 + 3", exp, sig } — answer is verified server-side.
  researchChallenge: () => get('/research-requests/challenge'),
  createResearchRequest: (body) => post('/research-requests', body),
  // Court / deep-research order (login required); server recomputes the price.
  // { id, status, price_eur, entity_count, created_at }
  createCourtOrder: (body) => post('/research-requests/court-order', body),

  // --- admin (superuser only) ----------------------------------------------
  adminResearchRequests: () => get('/admin/research-requests'),
  adminUsers: () => get('/admin/users'),

  // full profile + connections both ways (owners/managers + owns/manages) + builder extras
  entity: (key) => get(`/entities/${encodeURIComponent(key)}`),
  // ego ownership network: { center, key, depth, nodes:[…], edges:[…] }
  entityNetwork: (key, depth = 2) =>
    get(`/entities/${encodeURIComponent(key)}/network?depth=${depth}`),

  // --- auth (fastapi-users) ------------------------------------------------
  // login: form-encoded; returns the JWT string.
  login: async (email, password) =>
    (await post('/auth/login', { username: email, password }, { form: true })).access_token,
  // register a new email/password user (then the caller logs in).
  register: (email, password, name) => post('/auth/register', { email, password, name }),
  // current user: { id, email, name, tier, … }
  me: () => get('/users/me'),
  // Google: fetch the consent URL the browser should be sent to. Surfaces the
  // server's detail message (e.g. "not configured") so the modal can show it.
  googleAuthorizeUrl: async () => {
    const res = await fetch('/api/auth/google/authorize', { headers: { ...authHeaders() } })
    if (!res.ok) {
      let msg = 'Google sign-in is unavailable right now.'
      try { msg = (await res.json()).detail || msg } catch { /* non-JSON */ }
      throw new Error(msg)
    }
    return (await res.json()).authorization_url
  },
}
