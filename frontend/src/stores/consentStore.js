/* Cookie / analytics consent. Persists a single decision to localStorage and
 * gates Google Analytics. `decided` controls whether the consent banner is shown;
 * `analytics` is the granted/declined choice.
 *
 * The GA loader is inlined here on purpose: a separate file named e.g.
 * "analytics.js" is blocked by ad blockers (ERR_BLOCKED_BY_CLIENT) on filename
 * alone, which would break this module's import in dev. */
import { defineStore } from 'pinia'

const KEY = 'bg_consent_v1'

// GA4 measurement id. In production builds it defaults to our property; in dev it
// stays off (no GA pollution from local work) unless you set VITE_GA_ID in a
// .env.local. An explicit VITE_GA_ID always overrides. The id is not a secret —
// it ships in client JS by design. GA still only loads after consent (below).
const GA_ID = import.meta.env.VITE_GA_ID || (import.meta.env.PROD ? undefined : undefined)
let gaLoaded = false

/* Inject Google Analytics. Only runs once, and only when an id is configured.
 * Called after consent (Accept) or to rehydrate a returning visitor. The actual
 * googletagmanager.com script may still be blocked by a user's ad blocker — that
 * is expected and harmless; gtag() calls just queue to dataLayer. */
function loadGA() {
  if (gaLoaded || !GA_ID || typeof document === 'undefined') return
  gaLoaded = true
  window.dataLayer = window.dataLayer || []
  window.gtag = function gtag() { window.dataLayer.push(arguments) }
  window.gtag('js', new Date())
  // send_page_view: false — this is a History-mode SPA, so the initial config call
  // would only ever record the landing path. We send page_view events ourselves on
  // every route change (see trackPageview, called from App.vue's route watcher).
  window.gtag('config', GA_ID, { anonymize_ip: true, send_page_view: false })
  const s = document.createElement('script')
  s.async = true
  s.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(GA_ID)}`
  document.head.appendChild(s)
}

// Record one SPA pageview for the current URL. Call after GA is loaded and on
// every client-side route change. No-op if GA hasn't loaded (declined/blocked).
export function trackPageview() {
  if (typeof window.gtag !== 'function') return
  window.gtag('event', 'page_view', {
    page_location: window.location.href,
    page_path: window.location.pathname + window.location.search,
    page_title: document.title,
  })
}

function read() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (v && typeof v.analytics === 'boolean') return { decided: true, analytics: v.analytics }
  } catch { /* corrupt / unavailable — treat as undecided */ }
  return { decided: false, analytics: false }
}

export const useConsentStore = defineStore('consent', {
  state: () => read(),
  actions: {
    persist() {
      try {
        localStorage.setItem(KEY, JSON.stringify({ analytics: this.analytics, ts: Date.now() }))
      } catch { /* ignore storage failures */ }
    },
    // Inject GA now (used both on Accept and to rehydrate a returning visitor).
    enableAnalytics() { loadGA() },
    accept() {
      this.analytics = true
      this.decided = true
      this.persist()
      this.enableAnalytics()
      trackPageview()
    },
    decline() {
      this.analytics = false
      this.decided = true
      this.persist()
    },
    // Let a user re-open the choice (e.g. to withdraw consent later).
    reopen() { this.decided = false },
  },
})
