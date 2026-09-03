// Pure helpers for the neighbourhood deep-dive: time-series lookups + investment math.
// Standard apartment sizes (m²) used across ALL calculations.
export const ROOM_SQM = { едностаен: 40, двустаен: 60, тристаен: 100 }
// i18n keys for the display label (resolved with $t + the m² from ROOM_SQM in the
// component). The Cyrillic keys are property-type identifiers from the API and stay.
export const ROOM_LABEL_KEY = { едностаен: 'finance.room.one', двустаен: 'finance.room.two', тристаен: 'finance.room.three' }
export const ROOM_ORDER = ['едностаен', 'двустаен', 'тристаен']

// Healthy price-to-rent benchmark — the "golden standard" reference.
// 17.5 ≈ 5.7% gross yield; the normal healthy range is 15–20.
export const HEALTHY_PTR = 17.5

// Pick the series point for a given year: exact year, else nearest earlier, else earliest.
export function pickByYear(series, year) {
  if (!series || !series.length) return null
  const withYear = series.map((p) => ({ ...p, _y: new Date(p.period_date).getFullYear() }))
  const exact = withYear.filter((p) => p._y === year)
  if (exact.length) return exact[exact.length - 1]
  const earlier = withYear.filter((p) => p._y <= year)
  if (earlier.length) return earlier[earlier.length - 1]
  return withYear[0]
}

export function pickWageByYear(rows, year) {
  if (!rows || !rows.length) return null
  const exact = rows.find((r) => r.year === year)
  if (exact) return exact
  const earlier = rows.filter((r) => r.year <= year)
  if (earlier.length) return earlier[earlier.length - 1]
  return rows[0]
}

// Verdict bucket for a price-to-rent ratio (7-tier rule-of-thumb scale).
// Returns an i18n key (`labelKey`) — resolve with $t() at render. `tone` drives
// the colour and is language-agnostic.
export function ptrVerdict(ptr) {
  if (ptr == null || !isFinite(ptr)) return { labelKey: 'finance.verdict.na', tone: 'na' }
  if (ptr < 12) return { labelKey: 'finance.verdict.strongBuy', tone: 'buy' }
  if (ptr < 15) return { labelKey: 'finance.verdict.goodValue', tone: 'good' }
  if (ptr < 18) return { labelKey: 'finance.verdict.fair', tone: 'fair' }
  if (ptr < 20) return { labelKey: 'finance.verdict.stretched', tone: 'stretched' }
  if (ptr < 25) return { labelKey: 'finance.verdict.expensive', tone: 'expensive' }
  if (ptr < 30) return { labelKey: 'finance.verdict.overpriced', tone: 'overpriced' }
  return { labelKey: 'finance.verdict.extreme', tone: 'extreme' }
}

// Price-to-rent from overall €/m² values (per-m² cancels): sale ÷ (annual rent).
export function ptrOf(saleSqm, rentSqm) {
  if (!saleSqm || !rentSqm) return null
  const ptr = saleSqm / (rentSqm * 12)
  return isFinite(ptr) && ptr > 0 ? ptr : null
}

// Concrete bubble fills per PtR verdict tone — the single source of truth shared
// by the home bubble field and the deep-dive verdict badges.
export const PTR_TONE_COLOR = {
  buy: '#00a89c',
  good: 'var(--teal)',
  fair: '#ffd34d',
  stretched: '#ffa630',
  expensive: 'var(--coral)',
  overpriced: 'var(--pink)',
  extreme: 'var(--ink)',
  na: 'var(--neutral)',
}

// Standard amortised monthly payment.
export function monthlyPayment(principal, annualRatePct, years) {
  const r = annualRatePct / 100 / 12
  const n = years * 12
  if (r === 0) return principal / n
  return (principal * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1)
}

export const eur = (v) =>
  v == null ? '—' : '€' + Math.round(v).toLocaleString('en-US')

export const num = (v, d = 1) => (v == null || !isFinite(v) ? '—' : v.toFixed(d))
