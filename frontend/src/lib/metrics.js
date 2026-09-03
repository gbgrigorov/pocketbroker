// Bubble-field metrics. Each metric turns a map feature ({ sale_eur_sqm,
// rent_eur_sqm, ... }) into a bubble SIZE driver (bigger number = bigger bubble),
// a COLOUR, and the text shown under the name — plus how to rank in the sidebar.
// Designed to extend: add Growth / Transport here when their data lands.
import { ptrOf, ptrVerdict, PTR_TONE_COLOR } from './finance'

export const METRICS = {
  price: {
    key: 'price',
    // i18n keys — resolved with $t() in the consuming components (labels are
    // UI chrome; the metric logic below stays language-agnostic).
    labelKey: 'metrics.price.label',
    // size = the price itself (bigger = pricier)
    size: (f) => f.sale_eur_sqm,
    valueText: (f) => (f.sale_eur_sqm != null ? '€' + Math.round(f.sale_eur_sqm) : '—'),
    color: () => 'var(--pink)',
    legendKey: 'metrics.price.legend',
    rankLabelKey: 'metrics.price.rankLabel',
    rankValue: (f) => f.sale_eur_sqm,
    rankDir: 'desc',
    rankText: (f) =>
      f.sale_eur_sqm != null ? '€' + Math.round(f.sale_eur_sqm).toLocaleString('en-US') : '—',
  },
  ptr: {
    key: 'ptr',
    labelKey: 'metrics.ptr.label',
    // size = 1/PtR so a LOWER ratio (better buy) makes a BIGGER bubble
    size: (f) => {
      const p = ptrOf(f.sale_eur_sqm, f.rent_eur_sqm)
      return p ? 1 / p : null
    },
    valueText: (f) => {
      const p = ptrOf(f.sale_eur_sqm, f.rent_eur_sqm)
      return p ? 'PtR ' + p.toFixed(0) : '—'
    },
    color: (f) => PTR_TONE_COLOR[ptrVerdict(ptrOf(f.sale_eur_sqm, f.rent_eur_sqm)).tone],
    legendKey: 'metrics.ptr.legend',
    rankLabelKey: 'metrics.ptr.rankLabel',
    rankValue: (f) => ptrOf(f.sale_eur_sqm, f.rent_eur_sqm),
    rankDir: 'asc', // lower PtR ranks first
    rankText: (f) => {
      const p = ptrOf(f.sale_eur_sqm, f.rent_eur_sqm)
      return p ? 'PtR ' + p.toFixed(1) : '—'
    },
  },
  aqi: {
    key: 'aqi',
    labelKey: 'metrics.aqi.label',
    size: (f) => f.aqi,  // bigger = worse air quality
    valueText: (f) => (f.aqi != null ? 'AQI ' + Math.round(f.aqi) : '—'),
    color: (f) => {
      const v = f.aqi
      if (v == null) return 'var(--neutral)'
      if (v <= 50)  return '#22c55e'   // green — good
      if (v <= 100) return '#eab308'   // yellow — moderate
      if (v <= 150) return '#f97316'   // orange — unhealthy for sensitive groups
      return '#ef4444'                 // red — unhealthy
    },
    legendKey: 'metrics.aqi.legend',
    rankLabelKey: 'metrics.aqi.rankLabel',
    rankValue: (f) => f.aqi,
    rankDir: 'asc',  // lower AQI (cleaner) ranks first
    rankText: (f) => (f.aqi != null ? 'AQI ' + Math.round(f.aqi) : '—'),
  },
  pm25: {
    key: 'pm25',
    labelKey: 'metrics.pm25.label',
    size: (f) => f.pm25,  // bigger = more PM2.5
    valueText: (f) => (f.pm25 != null ? f.pm25.toFixed(1) + ' µg/m³' : '—'),
    color: (f) => {
      const v = f.pm25
      if (v == null) return 'var(--neutral)'
      if (v <= 12)  return '#22c55e'   // green — WHO annual guideline
      if (v <= 35)  return '#eab308'   // yellow — moderate
      if (v <= 55)  return '#f97316'   // orange — unhealthy
      return '#ef4444'                 // red — very unhealthy
    },
    legendKey: 'metrics.pm25.legend',
    rankLabelKey: 'metrics.pm25.rankLabel',
    rankValue: (f) => f.pm25,
    rankDir: 'asc',  // lower PM2.5 ranks first
    rankText: (f) => (f.pm25 != null ? f.pm25.toFixed(1) + ' µg/m³' : '—'),
  },
}

export const METRIC_ORDER = ['price', 'ptr', 'aqi', 'pm25']

// Air-quality metrics live in the sidebar (seasonal, citizen-sensor sourced),
// not the top metric strip. Everything else (price, ptr) stays in the top bar.
export const AIR_METRICS = ['aqi', 'pm25']

// Features ranked for the active metric (drops entities with no value).
export function rankFeatures(features, metricKey) {
  const m = METRICS[metricKey] || METRICS.price
  const rows = features
    .map((f) => ({ f, v: m.rankValue(f) }))
    .filter((r) => r.v != null)
  rows.sort((a, b) => (m.rankDir === 'asc' ? a.v - b.v : b.v - a.v))
  return rows.map((r) => ({
    slug: r.f.slug,
    name: r.f.name,
    text: m.rankText(r.f),
  }))
}
