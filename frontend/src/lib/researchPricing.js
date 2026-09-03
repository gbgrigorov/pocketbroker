// Court / deep-research order pricing — live estimate for the UI.
//
// ⚠️ KEEP IN SYNC with backend/app/pricing.py — that file is authoritative; the
// server recomputes the price on submit, so these numbers are for display only.
//
// Model:
//   single company, by EIK         -> €1
//   single company, by EIK + Name  -> 3× = €3   (fuzzier results)
//   whole network, by EIK          -> ceil(companies / 10) × €3
//   whole network, by EIK + Name   -> 3× the block total
// Only companies with an EIK are counted (persons have none).

export const COURT_SINGLE_EUR = 1.0
export const NETWORK_BLOCK_EUR = 3.0
export const BLOCK_SIZE = 10
export const NAME_MULTIPLIER = 3

const mult = (searchType) => (searchType === 'eik_name' ? NAME_MULTIPLIER : 1)
const round2 = (n) => Math.round(n * 100) / 100

// Number of billable companies in a network (kind === 'company' && has an EIK).
export function companyCount(nodes) {
  return (nodes || []).filter((n) => n.kind === 'company' && n.eik).length
}

export function quoteSingle(searchType) {
  return round2(COURT_SINGLE_EUR * mult(searchType))
}

export function quoteNetwork(count, searchType) {
  const blocks = count > 0 ? Math.ceil(count / BLOCK_SIZE) : 0
  return round2(blocks * NETWORK_BLOCK_EUR * mult(searchType))
}

// Dispatch on scope; returns the price in EUR.
export function quote(scope, count, searchType) {
  return scope === 'network' ? quoteNetwork(count, searchType) : quoteSingle(searchType)
}
