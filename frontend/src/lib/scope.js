// City-scope classifier for bubbles: is an entry part of the Sofia urban core
// ("sofia") or an outlying area ("extended")?
//
// "extended" =
//   1. Separate settlements — villages (с., slug `s-`) and the annexed towns
//      (гр. Банкя, гр. Нови Искър, slug `gr-`).
//   2. A few detached areas that are *officially* град-София quarters but sit far
//      from the contiguous city, so they don't belong in the default view:
//      the Кремиковци steel-plant exclaves (Кремиковци, Ботунец) and the
//      far-eastern Врана villa zones, tied to the villages Герман/Лозен.
// Everything else is Sofia city proper.
const EXTENDED_SLUGS = new Set([
  'kremikovtsi',
  'botunets',
  'botunets-2',
  'v-z-vrana-german',
  'v-z-vrana-lozen',
])

export function isExtended(slug) {
  return /^(s|gr)-/.test(slug || '') || EXTENDED_SLUGS.has(slug)
}
