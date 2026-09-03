// Per-route <title>/<meta description>/<link rel=canonical> for SEO + GA pageviews.
// History-mode routes are real URLs, so each view should set its own meta on load.
const DEFAULT_TITLE = 'BG INTEL — Sofia Market Intelligence'
const DEFAULT_DESC = 'Bulgarian real-estate market intelligence: neighbourhood price trends, developer ownership networks, and public-record signals.'

function ensureMeta(name) {
  let el = document.querySelector(`meta[name="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('name', name)
    document.head.appendChild(el)
  }
  return el
}

export function setPageMeta({ title, description } = {}) {
  document.title = title ? `${title} — BG INTEL` : DEFAULT_TITLE
  ensureMeta('description').setAttribute('content', description || DEFAULT_DESC)
  let canon = document.querySelector('link[rel="canonical"]')
  if (!canon) {
    canon = document.createElement('link')
    canon.setAttribute('rel', 'canonical')
    document.head.appendChild(canon)
  }
  canon.setAttribute('href', window.location.origin + window.location.pathname)
}

export function resetPageMeta() { setPageMeta({}) }
