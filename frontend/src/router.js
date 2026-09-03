// Minimal History-mode router (no dependency). Routes:
//   /                       → home (Bulgaria map — pick a city)
//   /c/<city>               → that city's neighbourhood bubble field
//   /c/<city>/n/<slug>      → neighbourhood deep-dive (city-scoped)
//   /entities               → entity browse (search any company/builder/person)
//   /e/<key>[/<slug>]       → single entity profile (light); slug is cosmetic/SEO
//   /e/<key>[/<slug>]/network → entity ego ownership-network (heavy graph)
//   /about                  → how-it-works explainer page
// Back-compat: /builders → entities, /b/<eik> → /e/<eik>,
//              /n/<slug> → Sofia neighbourhood (old single-city deep links).
//
// Old `#/...` hash bookmarks/links are converted to the equivalent path via
// history.replaceState on boot, so existing links keep working.
import { ref } from 'vue'

function redirectLegacyHash() {
  const h = window.location.hash
  if (h && h.startsWith('#/')) {
    history.replaceState(null, '', h.slice(1) + window.location.search)
  }
}
redirectLegacyHash()

function parse() {
  const p = decodeURIComponent(window.location.pathname)

  let m = p.match(/^\/c\/([^/]+)\/n\/([^/]+)$/)
  if (m) return { name: 'neighbourhood', section: 'estate', city: m[1], slug: m[2] }

  // Air-quality section mirrors the price flow on its own URLs.
  m = p.match(/^\/air-quality\/([^/]+)$/)
  if (m) return { name: 'city', section: 'air', city: m[1] }
  if (p === '/air-quality') return { name: 'home', section: 'air' }

  m = p.match(/^\/c\/([^/]+)$/)
  if (m) return { name: 'city', section: 'estate', city: m[1] }

  m = p.match(/^\/n\/([^/]+)$/) // legacy: assume Sofia
  if (m) return { name: 'neighbourhood', section: 'estate', city: 'sofia', slug: m[1] }

  // /certificate/<key>  or  /certificate/<key>/<slug>  → transparency certificate
  m = p.match(/^\/certificate\/([^/]+)(?:\/([^/]+))?$/)
  if (m) return { name: 'certificate', key: m[1], slug: m[2] || null }

  // /e/<key>/network  or  /e/<key>/<slug>/network
  m = p.match(/^\/(?:e|b)\/([^/]+)\/(?:([^/]+)\/)?network$/)
  if (m) return { name: 'entity-network', key: m[1], slug: m[2] || null }

  // /e/<key>/report  or  /e/<key>/<slug>/report  (hidden client deliverable)
  m = p.match(/^\/(?:e|b)\/([^/]+)\/(?:([^/]+)\/)?report$/)
  if (m) return { name: 'entity-report', key: m[1], slug: m[2] || null }

  // /e/<key>  or  /e/<key>/<slug>
  m = p.match(/^\/(?:e|b)\/([^/]+)(?:\/([^/]+))?$/)
  if (m) return { name: 'entity', key: m[1], slug: m[2] || null }

  if (p === '/entities' || p === '/builders') return { name: 'entities' }
  if (p === '/admin') return { name: 'admin' }
  if (p === '/location') return { name: 'location' }
  if (p === '/about') return { name: 'about' }
  if (p === '/terms') return { name: 'terms' }
  if (p === '/privacy') return { name: 'privacy' }
  if (p === '/disclaimer') return { name: 'disclaimer' }
  return { name: 'home', section: 'estate' }
}

const route = ref(parse())
let _prev = null

window.addEventListener('popstate', () => {
  _prev = route.value
  route.value = parse()
})

export function useRoute() { return route }

export function navigate(path) {
  if (path === window.location.pathname + window.location.search) return
  history.pushState(null, '', path)
  _prev = route.value
  route.value = parse()
}

export function goBack(fallback = '/entities') {
  if (_prev) { history.back() } else { navigate(fallback) }
}

// Build a `/e/<key>[/<slug>][suffix]` path, omitting the slug segment when unknown.
export function entityPath(key, slug, suffix = '') {
  return slug ? `/e/${key}/${slug}${suffix}` : `/e/${key}${suffix}`
}

// Path to a section's country map (city omitted) or city bubble field.
export function cityPath(city, section = 'estate') {
  const base = section === 'air' ? '/air-quality' : ''
  return city ? `${base || '/c'}/${city}` : base || '/'
}
