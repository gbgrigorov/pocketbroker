// Registry of authored research reports, keyed by ЕИК.
//
// The real authored analyses are kept out of this public mirror (they name
// private individuals and carry court findings). Only a fictional demo module
// ships here, so the feature stays runnable and its data shape stays documented.
//
// Add a report by creating a sibling data module (same shape as ./demo-stroy.js)
// and registering it here. `getReport(key)` accepts an ЕИК (or any entity key)
// and returns the report object, or null if none exists.

import demoStroy from './demo-stroy.js'

const REPORTS = {
  '999999999': demoStroy,
}

export function getReport(key) {
  return REPORTS[String(key)] || null
}

export function hasReport(key) {
  return Boolean(REPORTS[String(key)])
}
