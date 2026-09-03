<script setup>
/*
 * Сертификат за прозрачност и надеждност — ornate "diploma" certificate (landscape A3).
 * Hero is the live ownership NETWORK (the "we hide nothing" proof). Gold guilloché frame,
 * stat medallions, a boxing-style legal record, a foil seal + laurel wreath of trust.
 *
 * Bulgarian-only by design — copy hardcoded here (like DB content, which stays Cyrillic).
 * v1 case study: СЕНТЕР КОНСУЛТ ЕООД (103716382). Layout matches the approved mockup;
 * numbers are wired to real API data where we have it (the mockup's figures were
 * placeholders). Legal-outcome buckets use a per-EIK override; ADJUST PER COMPANY.
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { goBack, entityPath, navigate } from '../router'
import { useAuthStore } from '../stores/authStore'
import OwnershipGraph from '../components/OwnershipGraph.vue'

const props = defineProps({ ekey: String })
const auth = useAuthStore()

const profile = ref(null)
const net = ref({ nodes: [], edges: [], center: null })
const loading = ref(true)
const error = ref(null)

const EUR_RATE = 1.95583
const DEPTH = 2

async function load() {
  loading.value = true; error.value = null
  try {
    profile.value = await api.entity(props.ekey)
    document.title = `Сертификат · ${profile.value?.name || props.ekey}`
    net.value = auth.isAuthenticated
      ? await api.entityNetwork(props.ekey, DEPTH)
      : { nodes: [], edges: [], center: null }
  } catch (e) { error.value = String(e) } finally { loading.value = false }
}
watch(() => props.ekey, load, { immediate: true })
watch(() => auth.isAuthenticated, load)

// graph fills its column — measure the box, feed a px height to the D3 graph
const graphBox = ref(null)
const graphHeight = ref(440)
let ro
onMounted(() => {
  window.scrollTo(0, 0)
  ro = new ResizeObserver((es) => {
    const h = es[0]?.contentRect?.height
    if (h && Math.abs(h - graphHeight.value) > 8) graphHeight.value = Math.round(h)
  })
  if (graphBox.value) ro.observe(graphBox.value)
})
onBeforeUnmount(() => ro?.disconnect())
watch(graphBox, (el) => { if (el && ro) ro.observe(el) })

function printDoc() { window.print() }

// ── Legal record ─────────────────────────────────────────────────────────────
// Curated per company, keyed by ЕИК → FULL act title. Title (not act № alone) is
// the key because a company can hold two acts with the same № from different
// courts/years (e.g. ИМОТИ БЪЛГАРИЯ has a 2019 win AND a 2023 loss both "№ 150").
// Only used to CORRECT the text-classifier below where it misreads the outcome.
const OUTCOME_OVERRIDES = {
  '813070654': { // ИМОТИ БЪЛГАРИЯ — party in real cases both ways
    'Решение № 980 от 08.05.2013 — ОС Варна, в.гр.д. 983/2013': 'claimant',      // wins vs Енерго-Про
    'Решение № 150 от 21.02.2019 — ОС Варна, т.д. 439/2018': 'claimant',         // wins vs Армеец (Каско)
    'Решение № 418 от 04.10.2022 — ОС Варна, т.д. 832/2021': 'adverse',          // loses vs София Франс Ауто (1)
    'Решение № 150 от 05.05.2023 — Апел. съд Варна, в.т.д. 32/2023': 'adverse',  // appeal upholds loss (2)
    'Определение № 740 от 10.03.2025 — ВКС, к.т.д. 1735/2023': 'adverse',        // ВКС — loss final (3)
  },
  '103610351': { // ИМОТИ БЪЛГАРИЯ ИНВЕСТ (in the network)
    'Решение № 963 от 17.05.2019 — РС Варна, АНД 1179/2019': 'claimant',         // NAP sanction cut ~20×
  },
  '103716382': { // СЕНТЕР КОНСУЛТ — all stem from one 2009 loan dispute
    'Районен съд - Варна, Определение № 12860 от 29.11.2016 по гр.д. 7987/2016': 'defended',
    'Районен съд - Варна, Определение № 2416 от 06.03.2017 по гр.д. 7994/2016': 'defended',
    'Окръжен съд - Варна, Решение № 1316 от 02.11.2016 по в.гр.д. 2032/2016': 'claimant',
    'Районен съд - Варна, Определение № 12249 от 11.11.2016 по гр.д. 7994/2016': 'procedural',
    'Окръжен съд - Варна, Определение № 154 от 17.01.2017 по в.ч.т.д. 1734/2016': 'procedural',
  },
}
// Court acts dropped from the record entirely: manually reviewed name-matches where
// the entity is NOT a party (legalacts noise). Keyed by ЕИК → full title so an
// exclusion never leaks onto a different company. ADD ONLY AFTER READING THE ACT —
// never blanket-drop unclassified cases (that would hide a real one).
const EXCLUDED_TITLES = {
  '813070654': new Set([ // ИМОТИ БЪЛГАРИЯ mentioned only as buyer / insured / owner-victim
    'Решение № 2428 от 30.11.2016 — Админ. съд Варна, адм.д. 1937/2016',  // buyer of ideal parts
    'Решение № 28 от 03.02.2021 — ОС Варна, т.д. 951/2020',               // insured party in a regress claim
    'Присъда № 23 от 29.01.2018 — РС Варна, НОХД 5126/2017',              // criminal case vs a driver
  ]),
  '148077801': new Set([ // ДИНЕСО — appeals by other firms; ДИНЕСО non-party / role unconfirmed
    'Районен съд - Варна, Решение № 1328 от 16.11.2025 по АНД 443/2025',
    'Районен съд - Варна, Решение № 1327 от 16.11.2025 по АНД 442/2025',
    'Районен съд - Варна, Решение № 963 от 17.05.2019 по НАХД 1179/2019',
  ]),
}
// One dispute can span several acts (first instance → appeal → cassation). Group
// them so it counts as ONE case with one outcome, not N — дела = disputes, not
// rulings. Keyed ЕИК → groups of full act titles. Only collapses what's listed.
const CASE_GROUPS = {
  '813070654': [ // ИМОТИ БЪЛГАРИЯ — София Франс Ауто, ОС→Апелативен→ВКС, all adverse → 1 loss
    { outcome: 'adverse', titles: new Set([
      'Решение № 418 от 04.10.2022 — ОС Варна, т.д. 832/2021',
      'Решение № 150 от 05.05.2023 — Апел. съд Варна, в.т.д. 32/2023',
      'Определение № 740 от 10.03.2025 — ВКС, к.т.д. 1735/2023',
    ]) },
  ],
}
const hasOverride = (eik, title) => !!(eik && OUTCOME_OVERRIDES[eik]?.[title])
const isExcluded = (eik, title) => !!(eik && EXCLUDED_TITLES[eik]?.has(title))
function classify(sig, eik = profile.value?.eik) {
  const ov = eik && OUTCOME_OVERRIDES[eik]
  if (ov && ov[sig.title]) return ov[sig.title]
  const s = (sig.snippet || '') + ' ' + (sig.title || '')
  if (/осъжда|осъдител|обявява в несъстоятелност/i.test(s)) return 'adverse'
  if (/прекрат|недопустим|отхвърл|оставя без уважение/i.test(s)) return 'defended'
  if (/отменя|връща|нередовност|обжалва/i.test(s)) return 'procedural'
  if (/взискател|ищец|кредитор/i.test(s)) return 'claimant'
  return 'other'
}
// Collapse appeal-chain acts of one dispute into a single outcome (see CASE_GROUPS),
// then take a flat list of outcomes. Ungrouped acts pass through 1:1.
function outcomesOf(items) {  // items: [{ title, eik, outcome }]
  const seen = new Set(), out = []
  for (const it of items) {
    const g = (CASE_GROUPS[it.eik] || []).find((grp) => grp.titles.has(it.title))
    if (!g) { out.push(it.outcome); continue }
    const gid = it.eik + '|' + g.titles.values().next().value
    if (seen.has(gid)) continue           // this dispute already counted once
    seen.add(gid); out.push(g.outcome)
  }
  return out
}
// Fold a list of outcomes into the four displayed buckets.
const buckets = (outcomes) => ({
  total: outcomes.length,
  won: outcomes.filter((o) => o === 'defended' || o === 'claimant').length,
  lost: outcomes.filter((o) => o === 'adverse').length,
  open: outcomes.filter((o) => o === 'procedural').length,
})
const authed = computed(() => auth.isAuthenticated)
const dash = (v) => (authed.value ? v : '—')

// Row 1 — this company's own legal record.
const companyRec = computed(() => buckets(outcomesOf(
  (profile.value?.signals || [])
    .filter((s) => s.title && !isExcluded(profile.value?.eik, s.title))
    .map((s) => ({ title: s.title, eik: profile.value?.eik, outcome: classify(s) })))))

// Row 2 — the whole ownership network. Every node carries its own signals; a
// court act shared across sibling EIKs appears once per entity, so dedupe by
// title (preferring an instance whose node has a curated outcome override).
const networkRec = computed(() => {
  const byTitle = new Map()
  for (const n of (net.value.nodes || [])) {
    for (const s of (n.signals || [])) {
      if (!s.title || isExcluded(n.eik, s.title)) continue
      const ov = hasOverride(n.eik, s.title)
      const prev = byTitle.get(s.title)
      if (!prev || (ov && !prev.ov)) byTitle.set(s.title, { sig: s, eik: n.eik, ov })
    }
  }
  return buckets(outcomesOf([...byTitle.values()]
    .map(({ sig, eik }) => ({ title: sig.title, eik, outcome: classify(sig, eik) }))))
})
// Drives the two legal-record rows (same four metrics, different scope).
const legalRows = computed(() => [
  { key: 'company', cap: 'За дружеството', rec: companyRec.value },
  { key: 'network', cap: 'За мрежата', rec: networkRec.value },
])

// ── Network + company figures ────────────────────────────────────────────────
const nodesCount = computed(() => net.value.nodes?.length || 0)
const edgesCount = computed(() => net.value.edges?.length || 0)
const companyCount = computed(() => (net.value.nodes || []).filter((n) => n.kind === 'company' || n.is_builder).length)
const peopleCount = computed(() => (net.value.nodes || []).filter((n) => n.kind === 'person').length)
const isActive = computed(() => ['Активен', 'active'].includes(profile.value?.status))

// Capital shown in EUR (Bulgaria is euro-pegged; data is stored in лв.)
const eurLabel = (bgn) => {
  if (bgn == null) return '—'
  const eur = bgn / EUR_RATE
  return eur >= 1e6 ? (eur / 1e6).toFixed(1).replace('.', ',') + ' млн. €'
    : new Intl.NumberFormat('bg-BG').format(Math.round(eur)) + ' €'
}
const capitalLabel = computed(() => eurLabel(profile.value?.capital_bgn))
// Total registered capital across every company in the ownership network (EUR).
const totalCapitalLabel = computed(() => {
  if (!authed.value) return '—'
  const sum = (net.value.nodes || [])
    .filter((n) => n.kind === 'company' || n.is_builder)
    .reduce((acc, n) => acc + (Number(n.capital_bgn) || 0), 0)
  return sum > 0 ? eurLabel(sum) : '—'
})

// Years on the market, derived from the registration year (е.g. 2002 → 24 г.).
const yearsInBusiness = computed(() => {
  const y = profile.value?.founded_year
  return y ? issueYear - Number(y) : null
})
const yearsLabel = computed(() =>
  yearsInBusiness.value != null ? `${yearsInBusiness.value} г.` : '—')

// ── Данъчен принос — корпоративен данък (10% върху печалбата) ──────────────────
// DISABLED for now: public tax data is too fuzzy — reliable ГФО only exist from
// ~2008 (register launched 2008; flat 10% only since 2007), papagal locks recent
// years behind PRO, and a total can't honestly claim "since founding". Kept the
// scaffolding for later: to re-enable, add a per-EIK entry keyed ЕИК → { approx,
// years: { <year>: <eur> } } (exact from ГФО, or ≈10% × счетоводна печалба). The
// two tiles are v-if="taxInfo", so an empty map hides them.
const TAX_BY_EIK = {}
const taxInfo = computed(() => TAX_BY_EIK[profile.value?.eik] || null)
const taxYears = computed(() =>
  taxInfo.value ? Object.keys(taxInfo.value.years).map(Number).sort((a, b) => a - b) : [])
const lastTaxYear = computed(() => taxYears.value.at(-1) ?? null)
const fmtEur = (eur) => new Intl.NumberFormat('bg-BG').format(Math.round(eur)) + ' €'
const approx = (s) => (taxInfo.value?.approx ? '≈ ' : '') + s
const lastYearTaxLabel = computed(() =>
  taxInfo.value && lastTaxYear.value != null
    ? approx(fmtEur(taxInfo.value.years[lastTaxYear.value])) : '—')
const totalTaxLabel = computed(() =>
  taxInfo.value
    ? approx(fmtEur(Object.values(taxInfo.value.years).reduce((a, b) => a + b, 0))) : '—')

// ── Identity ─────────────────────────────────────────────────────────────────
const issuedDate = computed(() =>
  new Intl.DateTimeFormat('bg-BG', { day: '2-digit', month: 'long', year: 'numeric' }).format(new Date()))
const issueYear = new Date().getFullYear()
const certNo = computed(() => `PB-${profile.value?.eik || props.ekey}-${issueYear}`)
const legalFormShort = () => {
  const m = (profile.value?.legal_form || '').match(/\(([^)]+)\)/)
  return m ? m[1] : profile.value?.legal_form || ''
}
const subjectName = computed(() => {
  const p = profile.value
  if (!p) return ''
  const sh = legalFormShort()
  return sh && !p.name.includes(sh) ? `${p.name} ${sh}` : p.name
})

// ── Decorative geometry ──────────────────────────────────────────────────────
const qr = computed(() => {
  const n = 23, m = Array.from({ length: n }, () => Array(n).fill(false))
  const seedStr = certNo.value
  let s = 7
  for (const c of seedStr) s = (s * 31 + c.charCodeAt(0)) >>> 0
  const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff }
  const finder = (r0, c0) => {
    for (let i = 0; i < 7; i++) for (let j = 0; j < 7; j++) {
      const border = i === 0 || i === 6 || j === 0 || j === 6
      const core = i >= 2 && i <= 4 && j >= 2 && j <= 4
      if (border || core) m[r0 + i][c0 + j] = true
    }
  }
  finder(0, 0); finder(0, n - 7); finder(n - 7, 0)
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
    const inF = (r < 8 && c < 8) || (r < 8 && c >= n - 8) || (r >= n - 8 && c < 8)
    if (!inF && rnd() > 0.52) m[r][c] = true
  }
  return m
})

const GOLD = '#b89243'
</script>

<template>
  <div class="cert-page">
    <div class="bar no-print">
      <button class="ghost" @click="goBack('/entities')">← Назад</button>
      <span class="bartag">PocketBroker · Сертификат за прозрачност</span>
      <button class="print-btn" @click="printDoc">Запази като PDF (A3)</button>
    </div>

    <div v-if="error" class="banner">{{ error }}</div>
    <div v-else-if="loading" class="loading">Зареждане…</div>

    <article v-else-if="profile" class="sheet">
      <div class="frame">
        <!-- ornate corners -->
        <svg v-for="pos in ['tl','tr','bl','br']" :key="pos" class="ornament" :class="pos" viewBox="0 0 90 90" aria-hidden="true">
          <path d="M6 84 Q6 6 84 6" fill="none" :stroke="GOLD" stroke-width="2" />
          <path d="M6 60 Q6 6 60 6" fill="none" :stroke="GOLD" stroke-width="1" />
          <path d="M14 40 Q14 14 40 14 Q26 22 22 30 Q18 36 14 40Z" :fill="GOLD" opacity="0.85" />
          <circle cx="10" cy="10" r="2.4" :fill="GOLD" />
        </svg>

        <div class="doc">
          <!-- ── header ────────────────────────────────────────────── -->
          <header class="head">
            <div class="logo">
              <span class="logo__mark">PB</span>
              <span class="logo__txt">
                <span class="logo__name">POCKETBROKER</span>
                <span class="logo__kicker">Регистър на прозрачни строители</span>
              </span>
            </div>
            <div class="head__right">
              <div class="head__cert">СЕРТИФИКАТ № <b>{{ certNo }}</b></div>
              <div class="head__date">Издаден на {{ issuedDate }}</div>
              <div class="mini-div"><span></span><i></i><span></span></div>
            </div>
          </header>

          <!-- ── body ──────────────────────────────────────────────── -->
          <div class="body">
            <!-- LEFT -->
            <div class="left">
              <h1 class="title">Сертификат<br />за прозрачност <span>и</span><br />надеждност</h1>
              <div class="divider"><span></span><i></i><span></span></div>

              <div class="subject">
                <div class="subject__name">{{ subjectName }}</div>
                <div class="subject__eik">ЕИК {{ profile.eik }}</div>
                <div class="subject__sub">Публично верифициран строителен профил</div>
                <div class="subject__status">
                  {{ profile.status || 'Активен' }}
                  <svg viewBox="0 0 24 24" class="ok-badge"><circle cx="12" cy="12" r="11" fill="#15a89b"/><path d="M7 12.5l3.2 3.2L17 8.5" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
              </div>

              <!-- ПРОЗРАЧНОСТ В ЧИСЛА -->
              <div class="sec-head"><i></i>Прозрачност в числа<i></i></div>
              <div class="stats">
                <div class="stat">
                  <span class="ic"><svg class="ico" viewBox="0 0 24 24"><rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M16 6h.01M8 10h.01M16 10h.01M8 14h.01M16 14h.01"/></svg></span>
                  <span class="stat__b"><span class="lbl">Дружества в мрежата</span><span class="big">{{ dash(companyCount) }}</span></span>
                </div>
                <div class="stat">
                  <span class="ic"><svg class="ico" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></span>
                  <span class="stat__b"><span class="lbl">Съдружници / партньори</span><span class="big">{{ dash(peopleCount) }}</span></span>
                </div>
                <div class="stat">
                  <span class="ic"><svg class="ico" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg></span>
                  <span class="stat__b"><span class="lbl">Връзки в структурата</span><span class="big">{{ dash(edgesCount) }}</span></span>
                </div>
                <div class="stat">
                  <span class="ic"><svg class="ico" viewBox="0 0 24 24"><path d="M8 2v4M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg></span>
                  <span class="stat__b"><span class="lbl">Години на пазара</span><span class="big">{{ yearsLabel }}</span></span>
                </div>
                <div class="stat">
                  <span class="ic"><svg class="ico" viewBox="0 0 24 24"><circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/></svg></span>
                  <span class="stat__b"><span class="lbl">Капитал на дружеството</span><span class="big sm">{{ capitalLabel }}</span></span>
                </div>
                <div class="stat">
                  <span class="ic"><svg class="ico" viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/></svg></span>
                  <span class="stat__b"><span class="lbl">Общ капитал в мрежата</span><span class="big sm">{{ totalCapitalLabel }}</span></span>
                </div>
                <div v-if="taxInfo" class="stat">
                  <span class="ic"><svg class="ico" viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 15l6-6"/><circle cx="9.5" cy="9" r="1"/><circle cx="14.5" cy="15" r="1"/></svg></span>
                  <span class="stat__b"><span class="lbl">Корпоративен данък · {{ lastTaxYear }}</span><span class="big sm">{{ lastYearTaxLabel }}</span></span>
                </div>
                <div v-if="taxInfo" class="stat">
                  <span class="ic"><svg class="ico" viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/></svg></span>
                  <span class="stat__b"><span class="lbl">Общо внесен данък</span><span class="big sm">{{ totalTaxLabel }}</span></span>
                </div>
              </div>

              <!-- ПРАВЕН РЕКОРД — company row + network row -->
              <div class="sec-head"><i></i>Правен рекорд<i></i></div>
              <div class="legal-rows">
                <div v-for="row in legalRows" :key="row.key" class="legal-row">
                  <div class="legal-cap">{{ row.cap }}</div>
                  <div class="legal">
                    <div class="lg">
                      <span class="ic"><svg class="ico-solid" viewBox="0 0 512 512"><path d="M318.6 9.4c-12.5-12.5-32.8-12.5-45.3 0l-120 120c-12.5 12.5-12.5 32.8 0 45.3l16 16c12.5 12.5 32.8 12.5 45.3 0l4-4 49.4 49.4-4 4c-12.5 12.5-12.5 32.8 0 45.3l16 16c12.5 12.5 32.8 12.5 45.3 0l120-120c12.5-12.5 12.5-32.8 0-45.3l-16-16c-12.5-12.5-32.8-12.5-45.3 0l-4 4-49.4-49.4 4-4c12.5-12.5 12.5-32.8 0-45.3l-16-16zM4.7 427.3c-6.2 6.2-6.2 16.4 0 22.6l28.3 28.3c6.2 6.2 16.4 6.2 22.6 0l173.7-173.6-50.9-50.9L4.7 427.3z"/></svg></span>
                      <span class="lg__b"><b class="lg__n">{{ dash(row.rec.total) }}</b><b class="lg__l">дела</b></span>
                    </div>
                    <div class="lg">
                      <span class="ic"><svg class="ico-solid" viewBox="0 0 24 24"><path d="M5.166 2.621v.858c-1.035.148-2.059.33-3.071.543a.75.75 0 0 0-.584.859 6.753 6.753 0 0 0 6.138 5.6 6.73 6.73 0 0 0 2.743 1.346A6.707 6.707 0 0 1 9.279 15H8.54c-1.036 0-1.875.84-1.875 1.875V19.5h-.75a2.25 2.25 0 0 0-2.25 2.25c0 .414.336.75.75.75h15a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-2.25-2.25h-.75v-2.625c0-1.036-.84-1.875-1.875-1.875h-.739a6.706 6.706 0 0 1-1.112-3.173 6.73 6.73 0 0 0 2.743-1.347 6.753 6.753 0 0 0 6.139-5.6.75.75 0 0 0-.585-.858 47.077 47.077 0 0 0-3.07-.543V2.62a.75.75 0 0 0-.658-.744 49.22 49.22 0 0 0-6.093-.377c-2.063 0-4.096.128-6.093.377a.75.75 0 0 0-.657.744Zm0 2.629c0 1.196.312 2.32.857 3.294A5.266 5.266 0 0 1 3.16 5.337a45.6 45.6 0 0 1 2.006-.343v.256Zm13.5 0v-.256c.674.1 1.343.214 2.006.343a5.265 5.265 0 0 1-2.863 3.207 6.72 6.72 0 0 0 .857-3.294Z"/></svg></span>
                      <span class="lg__b"><b class="lg__n">{{ dash(row.rec.won) }}</b><b class="lg__l">спечелени</b></span>
                    </div>
                    <div class="lg">
                      <span class="ic"><svg class="ico-lost" viewBox="0 0 24 24"><circle class="lost-disc" cx="12" cy="12" r="10"/><path class="lost-x" d="M8.8 8.8l6.4 6.4M15.2 8.8l-6.4 6.4"/></svg></span>
                      <span class="lg__b"><b class="lg__n">{{ dash(row.rec.lost) }}</b><b class="lg__l">загубено</b></span>
                    </div>
                    <div class="lg">
                      <span class="ic"><svg class="ico-solid" viewBox="0 0 24 24"><path d="M4.755 10.059a7.5 7.5 0 0 1 12.548-3.364l1.903 1.903h-3.183a.75.75 0 1 0 0 1.5h4.992a.75.75 0 0 0 .75-.75V4.356a.75.75 0 0 0-1.5 0v3.18l-1.9-1.9A9 9 0 0 0 3.306 9.67a.75.75 0 1 0 1.45.388Zm15.408 3.352a.75.75 0 0 0-.919.53 7.5 7.5 0 0 1-12.548 3.364l-1.902-1.903h3.183a.75.75 0 0 0 0-1.5H2.984a.75.75 0 0 0-.75.75v4.992a.75.75 0 0 0 1.5 0v-3.18l1.9 1.9a9 9 0 0 0 15.059-4.035.75.75 0 0 0-.53-.918Z"/></svg></span>
                      <span class="lg__b"><b class="lg__n">{{ dash(row.rec.open) }}</b><b class="lg__l">текущи</b></span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="legal__note">Данни от публични регистри</div>
            </div>

            <!-- RIGHT: network hero -->
            <div class="right">
              <figure ref="graphBox" class="graph-box">
                <OwnershipGraph
                  v-if="authed && net.nodes.length"
                  :nodes="net.nodes" :edges="net.edges" :center-id="net.center"
                  :center-fill="GOLD" :height="graphHeight" :spacing="1.5" label-mode="key" />
                <div v-else class="graph-gate">
                  <div class="graph-gate__lock">🔒</div>
                  <p>Пълната структура на собствеността и съдебният регистър се показват на вписани потребители.</p>
                  <button class="netbtn no-print" @click="auth.openModal()">Вход за пълни данни</button>
                </div>
              </figure>
              <div v-if="authed && net.nodes.length" class="legend">
                <span><i class="d person"></i>физическо лице</span>
                <span><i class="d company"></i>фирма</span>
                <span><i class="d signal"></i>ключово лице / сигнал</span>
                <span><i class="d edge"></i>връзка на собственост</span>
              </div>
            </div>
          </div>

          <!-- ── footer ────────────────────────────────────────────── -->
          <footer class="foot">
            <div class="foot__left">
              <svg class="qr" viewBox="0 0 23 23" shape-rendering="crispEdges" aria-hidden="true">
                <rect width="23" height="23" fill="#fff" />
                <template v-for="(row, r) in qr" :key="r">
                  <rect v-for="(on, c) in row" v-show="on" :key="r + '-' + c" :x="c" :y="r" width="1" height="1" :fill="'#1c1813'" />
                </template>
              </svg>
              <div class="verify">
                <div class="verify__h">Провери сертификата</div>
                <div class="verify__u">pocketbroker.bg/verify</div>
                <div class="verify__id">ID: {{ certNo }}</div>
              </div>
            </div>

            <div class="foot__center">
              <img class="stamp stamp--pb" src="/pb-stamp.png" alt="PocketBroker — верифициран печат" />
            </div>

            <div class="foot__right">
              <img class="stamp stamp--ai" src="/ai-stamp.png" alt="AI Verified — доверие, прозрачност, отговорност" />
            </div>
          </footer>
        </div>
      </div>
    </article>
  </div>
</template>

<style scoped>
.cert-page {
  --font-title: 'Archivo', 'Space Grotesk', sans-serif;
  --gold: #b89243; --gold-d: #8c6a26; --gold-l: #d8b860;
  --paper: #f6f0df; --ink: #1c1813; --red: #d2402c; --muted: #8a7f66;
  min-height: 100vh; background: #ece4cf; padding: 0 0 60px;
}

/* toolbar */
.bar { display: flex; align-items: center; gap: 14px; position: sticky; top: 0; z-index: 5; padding: 12px 20px; border-bottom: 2px solid var(--ink); background: #fff; }
.bartag { font-family: var(--font-mono); font-size: 11px; color: #555; }
.ghost { border: 2px solid var(--ink); background: #fff; box-shadow: 3px 3px 0 0 var(--ink); padding: 6px 12px; font-weight: 700; cursor: pointer; }
.print-btn { margin-left: auto; border: 2px solid var(--ink); background: var(--gold); color: #fff; box-shadow: 3px 3px 0 0 var(--ink); padding: 8px 14px; font-weight: 800; font-family: var(--font-display); text-transform: uppercase; cursor: pointer; }
.ghost:active, .print-btn:active { transform: translate(2px, 2px); box-shadow: 1px 1px 0 0 var(--ink); }
.banner { margin: 16px 20px; border: 2px solid var(--ink); background: var(--red); color: #fff; padding: 10px; }
.loading { padding: 60px; font-size: 24px; font-family: var(--font-display); }

/* ── sheet / frame ─────────────────────────────────────────────────────────── */
.sheet { width: min(98vw, 1480px); aspect-ratio: 1.414 / 1; margin: 26px auto; background:
  radial-gradient(120% 120% at 50% 35%, #fbf6e9 0%, var(--paper) 55%, #efe6cd 100%);
  box-shadow: 0 18px 50px rgba(0,0,0,0.28); position: relative; }
.frame { position: absolute; inset: 14px; border: 3px solid var(--gold); }
.frame::before { content: ''; position: absolute; inset: 6px; border: 1px solid var(--gold); opacity: 0.7; pointer-events: none; }
.ornament { position: absolute; width: 64px; height: 64px; }
.ornament.tl { top: 4px; left: 4px; }
.ornament.tr { top: 4px; right: 4px; transform: scaleX(-1); }
.ornament.bl { bottom: 4px; left: 4px; transform: scaleY(-1); }
.ornament.br { bottom: 4px; right: 4px; transform: scale(-1, -1); }

/* keep header/footer clear of the corner ornaments (≈64px flourishes) */
.doc { position: absolute; inset: 40px 46px; display: flex; flex-direction: column; color: var(--ink); }

/* ── header ────────────────────────────────────────────────────────────────── */
.head { display: flex; justify-content: space-between; align-items: flex-start; }
.logo { display: flex; align-items: center; gap: 8px; }
.logo__mark { display: grid; place-items: center; width: 30px; height: 30px; background: var(--ink); color: var(--gold-l); font-family: var(--font-display); font-weight: 800; font-size: 14px; border-radius: 5px; }
.logo__name { font-family: var(--font-title); font-weight: 800; font-size: 16px; letter-spacing: -0.01em; line-height: 1; display: block; }
.logo__kicker { font-family: 'Playfair Display', serif; font-style: italic; font-size: 8px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--gold-d); display: block; margin-top: 3px; }
.head__right { text-align: right; }
.head__cert { font-family: 'Playfair Display', serif; font-size: 14px; letter-spacing: 0.08em; color: var(--gold-d); text-transform: uppercase; }
.head__cert b { color: var(--ink); }
.head__date { font-family: 'Playfair Display', serif; font-style: italic; font-size: 12px; color: var(--muted); margin-top: 3px; }
.mini-div { display: flex; align-items: center; justify-content: flex-end; gap: 6px; margin-top: 7px; }
.mini-div span { height: 1px; width: 60px; background: var(--gold); }
.mini-div i { width: 6px; height: 6px; background: var(--gold); transform: rotate(45deg); }

/* ── body ──────────────────────────────────────────────────────────────────── */
/* minmax(0,1fr) pins the row to the fixed A3 body height so tall left-column
   content can't stretch the grid — keeps the layout A3 and the (absolutely
   positioned) legend anchored in one place. */
.body { display: grid; grid-template-columns: 40% 1fr; grid-template-rows: minmax(0, 1fr); gap: 26px; flex: 1; min-height: 0; }
.left { display: flex; flex-direction: column; min-width: 0; min-height: 0; }

.title { font-family: var(--font-title); font-weight: 900; text-transform: uppercase; font-size: clamp(30px, 3.6vw, 54px); line-height: 0.94; letter-spacing: -0.022em; margin: 4px 0 0; color: #14100c; }
.title span { color: var(--red); }

.divider { display: flex; align-items: center; gap: 8px; margin: 16px 0; }
.divider span { height: 1.5px; background: var(--gold); flex: 1; }
.divider span:first-child { flex: 0 0 26px; }
.divider i { width: 7px; height: 7px; background: var(--gold); transform: rotate(45deg); }

.subject { margin-bottom: 18px; }
.subject__name { font-family: var(--font-title); font-weight: 800; font-size: clamp(20px, 2.1vw, 30px); line-height: 1; letter-spacing: -0.01em; }
.subject__eik { font-family: 'Playfair Display', serif; font-size: 15px; letter-spacing: 0.06em; color: var(--gold-d); margin-top: 6px; }
.subject__sub { font-family: 'Playfair Display', serif; font-style: italic; font-size: 13px; color: var(--muted); margin-top: 6px; }
.subject__status { display: inline-flex; align-items: center; gap: 7px; font-family: var(--font-title); font-weight: 800; text-transform: uppercase; color: #0eafa5; font-size: 18px; margin-top: 10px; letter-spacing: 0.02em; }
.ok-badge { width: 19px; height: 19px; }

.sec-head { display: flex; align-items: center; gap: 10px; font-family: var(--font-head); font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em; font-size: 14px; color: var(--gold-d); margin: 22px 0 14px; }
.sec-head::before, .sec-head::after { content: ''; height: 1px; background: var(--gold); flex: 1; opacity: 0.7; }
.sec-head i { width: 5px; height: 5px; background: var(--gold); transform: rotate(45deg); flex: none; }

/* stat tiles — circular gold icon badge + label + premium value */
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px 18px; padding: 4px 0 10px; }
.stat { display: grid; grid-template-columns: 42px 1fr; align-items: center; gap: 11px; min-height: 54px; }
.ic { width: 40px; height: 40px; border: 1.5px solid var(--gold); border-radius: 50%; background: rgba(184, 146, 67, 0.07); display: grid; place-items: center; color: #8a6725; }
.ico { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 2.15; stroke-linecap: round; stroke-linejoin: round; }
.ic.red { color: var(--red); }
.stat__b { display: flex; flex-direction: column; min-width: 0; }
.lbl { font-family: var(--font-head); font-weight: 700; font-size: 8.5px; line-height: 1.15; letter-spacing: 0.095em; text-transform: uppercase; color: var(--muted); margin-bottom: 5px; }
.big { font-family: var(--font-title); font-weight: 900; font-size: 25px; line-height: 0.95; color: #14100c; }
.big.sm { font-size: 18px; }
.big.teal { color: #0eafa5; }

/* legal record — company row + network row, each a compact scorecard */
.legal-rows { display: flex; flex-direction: column; gap: 10px; padding-top: 2px; }
.legal-cap { display: flex; align-items: center; gap: 9px; font-family: var(--font-head); font-weight: 700; font-size: 8.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--gold-d); margin-bottom: 7px; }
.legal-cap::after { content: ''; height: 1px; background: rgba(184, 146, 67, 0.5); flex: 1; }
.legal { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.legal-row + .legal-row { padding-top: 9px; border-top: 1px solid rgba(184, 146, 67, 0.45); }
.lg { display: flex; align-items: center; justify-content: center; gap: 9px; }
.lg .ic { width: auto; height: auto; border: none; background: none; color: var(--gold-d); flex: none; }
.ico-solid { width: 28px; height: 28px; fill: currentColor; stroke: none; }
.lg .ic.red { color: var(--red); }
/* загубено: solid red disc with a crisp white X drawn on top (not cut out) */
.ico-lost { width: 28px; height: 28px; }
.ico-lost .lost-disc { fill: var(--red); }
.ico-lost .lost-x { fill: none; stroke: #fff; stroke-width: 2.3; stroke-linecap: round; }
.lg__b { display: flex; flex-direction: column; align-items: flex-start; line-height: 1; }
.lg__n { font-family: var(--font-title); font-weight: 900; font-size: 24px; line-height: 0.85; color: #14100c; }
.lg__l { font-family: var(--font-head); font-weight: 700; font-size: 8.5px; letter-spacing: 0.09em; text-transform: uppercase; color: var(--muted); margin-top: 4px; }
.legal__note { font-family: 'Playfair Display', serif; font-style: italic; font-size: 10px; color: var(--muted); margin-top: 12px; text-align: center; border-top: 1px solid rgba(184, 146, 67, 0.65); padding-top: 9px; }

/* ── network hero ──────────────────────────────────────────────────────────── */
.right { display: flex; flex-direction: column; min-width: 0; min-height: 0; position: relative; }
.graph-box { margin: 0; flex: 1; min-height: 0; position: relative; }
.graph-box :deep(.graph) { border: none !important; box-shadow: none !important; background: transparent !important; }
.graph-gate { height: 100%; min-height: 300px; border: 1.5px solid var(--gold); background: rgba(255,255,255,0.35); display: grid; place-content: center; text-align: center; gap: 12px; padding: 26px; }
.graph-gate__lock { font-size: 42px; }
.graph-gate p { max-width: 360px; margin: 0 auto; color: var(--muted); font-size: 13px; line-height: 1.5; font-family: 'Playfair Display', serif; }

/* legend sits as a vertical list at the lower-right of the graph (per mockup) */
.legend { position: absolute; right: 6px; bottom: 12px; display: flex; flex-direction: column; align-items: flex-start; gap: 8px; font-family: var(--font-mono); font-size: 10px; color: #5a513c; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.d { width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid var(--ink); }
.d.person { background: #ff6b47; } .d.company { background: #2b6bff; } .d.signal { background: #ffd400; }
.d.edge { width: 16px; height: 0; border: none; border-top: 2px solid #00b3a8; border-radius: 0; }

.netbtn { border: 2px solid var(--ink); background: #fff; box-shadow: 3px 3px 0 0 var(--ink); padding: 7px 13px; font-weight: 800; font-family: var(--font-display); text-transform: uppercase; font-size: 12px; cursor: pointer; }
.netbtn:active { transform: translate(2px, 2px); box-shadow: 1px 1px 0 0 var(--ink); }
.ghost-net { align-self: flex-end; margin-top: 8px; }

/* ── footer ────────────────────────────────────────────────────────────────── */
.foot { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; border-top: 1.5px solid var(--gold); padding-top: 12px; margin-top: 8px; }
.foot__left { display: flex; align-items: center; gap: 12px; }
.qr { width: 76px; height: 76px; border: 3px solid var(--ink); background: #fff; padding: 2px; box-sizing: border-box; }
.verify__h { font-family: 'Playfair Display', serif; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; font-size: 11px; color: var(--ink); }
.verify__u { font-family: var(--font-mono); font-size: 11px; color: var(--gold-d); margin-top: 4px; }
.verify__id { font-family: var(--font-mono); font-size: 10px; color: var(--muted); margin-top: 2px; }

.foot__center { display: flex; align-items: center; justify-content: center; }
.stamp { display: block; height: auto; }
/* PB stamp is the footer centerpiece — pulled up with a negative margin (so it
   doesn't inflate the footer height) to straddle the gold rule like a punched seal. */
.stamp--pb { position: relative; z-index: 2; margin-top: -66px; width: 178px; filter: drop-shadow(2px 3px 4px rgba(0,0,0,0.28)); }

.foot__right { display: flex; justify-content: flex-end; }
.stamp--ai { width: 126px; filter: drop-shadow(1px 2px 3px rgba(0,0,0,0.22)); }

/* ── print ─────────────────────────────────────────────────────────────────── */
@media print {
  @page { size: A3 landscape; margin: 0; }
  html, body { margin: 0 !important; padding: 0 !important; background: #fff !important; }
  .no-print { display: none !important; }
  /* Print the cream fill + gold/colour exactly — browsers drop CSS background
     colours/gradients in print unless we opt in with print-color-adjust. */
  .cert-page, .cert-page * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  .cert-page { min-height: 0; background: #fff; padding: 0; }
  /* The sheet becomes exactly one A3 landscape page. A DEFINITE height is the key:
     the inner .doc is absolutely positioned, so without it the layout reflows and
     spills onto a second page. overflow:hidden guards against a hairline overflow. */
  .sheet {
    width: 420mm; height: 297mm; aspect-ratio: auto;
    margin: 0; box-shadow: none; overflow: hidden;
    break-inside: avoid; page-break-inside: avoid;
  }
}
</style>
