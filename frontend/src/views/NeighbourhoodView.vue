<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import AppLink from '../components/AppLink.vue'
import { setPageMeta } from '../lib/pageMeta'
import PriceChart from '../components/PriceChart.vue'
import PtrChart from '../components/PtrChart.vue'
import BubbleCluster from '../components/BubbleCluster.vue'
import {
  ROOM_ORDER, ROOM_LABEL_KEY, ROOM_SQM, HEALTHY_PTR,
  pickByYear, pickWageByYear, ptrVerdict, ptrOf, monthlyPayment, eur, num,
} from '../lib/finance'
import { useIsMobile } from '../lib/useIsMobile'

const props = defineProps({ slug: String, city: { type: String, default: 'sofia' } })
const { t } = useI18n()

// Phones get a full-width square compass ring with bigger bubbles.
const isMobile = useIsMobile()

const MIN = 1995
const MAX = 2026
const year = ref(MAX)

const state = reactive({ loading: true, error: null })
const meta = ref(null)
const sale = ref({ series: [], by_type: {} })
const rent = ref({ series: [], by_type: {} })
const neighbours = ref([])
const gold = ref([])
const wage = ref([])

// Mortgage inputs (BG market defaults — editable)
const mortgage = reactive({ downPct: 15, ratePct: 2.9, term: 30 })

async function load(slug, city) {
  state.loading = true
  state.error = null
  try {
    const [m, s, r, n, g, w] = await Promise.all([
      api.neighbourhood(slug, city), api.prices(slug, 'sale', city), api.prices(slug, 'rent', city),
      api.neighbours(slug, city), api.gold(), api.minWage(),
    ])
    meta.value = m; sale.value = s; rent.value = r
    neighbours.value = n; gold.value = g; wage.value = w
    setPageMeta({
      title: meta.value?.name,
      description: t('meta.neighbourhoodDesc', { name: meta.value?.name, city }),
    })
  } catch (e) {
    state.error = String(e)
  } finally {
    state.loading = false
  }
}
watch(() => [props.slug, props.city], ([s, c]) => s && load(s, c), { immediate: true })

// City-scoped deep-link prefix so a neighbour click stays within this city.
const linkPrefix = computed(() => `/c/${props.city}/n`)

// Seasonal air quality for this area, following the year slider. `meta.air` is the
// full per-year dict ({ "2024": { winter:{...}, summer:{...} }, … }); like the
// bubble field, we snap to the nearest available year so the table never blanks out
// on a year we don't have — the header shows the year actually shown.
const airByYear = computed(() => meta.value?.air || null)
const air = computed(() => {
  const by = airByYear.value
  const years = by ? Object.keys(by) : []
  if (!years.length) return null
  let key = String(year.value)
  if (!by[key]) {
    key = years.reduce((best, y) =>
      Math.abs(Number(y) - year.value) < Math.abs(Number(best) - year.value) ? y : best)
  }
  const cell = by[key]
  return { year: Number(key), winter: cell.winter || null, summer: cell.summer || null }
})
const fmtPm = (v) => (v != null ? v.toFixed(1) : '—')
const fmtAqi = (v) => (v != null ? Math.round(v) : '—')

const centerValue = computed(() => pickByYear(sale.value.series, year.value)?.price_eur_sqm ?? null)
const eurLabel = (v) => (v != null ? '€' + Math.round(v) : '—')
// Center + directional satellites as BubbleCluster nodes.
const clusterNodes = computed(() => {
  const center = {
    slug: props.slug, name: meta.value?.name || '', value: centerValue.value,
    isCenter: true, color: 'var(--pink)', label: eurLabel(centerValue.value),
  }
  const sats = neighbours.value.map((nb) => {
    const v = pickByYear(nb.series, year.value)?.price_eur_sqm ?? null
    return {
      slug: nb.slug, name: nb.name, value: v, direction: nb.direction,
      color: 'var(--teal)', label: eurLabel(v),
    }
  })
  return [center, ...sats]
})

// Price-to-Rent ratio over time: join sale + rent overall €/m² series by year.
// Per-m² cancels in ptrOf, so this single line represents the whole neighbourhood.
const ptrSeries = computed(() => {
  const rentByYear = new Map(
    (rent.value.series || []).map((p) => [new Date(p.period_date).getFullYear(), p.price_eur_sqm]),
  )
  return (sale.value.series || [])
    .map((p) => {
      const ptr = ptrOf(p.price_eur_sqm, rentByYear.get(new Date(p.period_date).getFullYear()))
      return ptr != null ? { period_date: p.period_date, ptr } : null
    })
    .filter(Boolean)
})

const goldAtYear = computed(() => pickByYear(gold.value.map((r) => ({ period_date: r.period_date, v: r.price_eur_per_gram })), year.value)?.v ?? null)
const wageAtYear = computed(() => pickWageByYear(wage.value, year.value)?.amount_eur ?? null)

// Reference rates shown in the affordability table headers, tracking the slider year.
const goldRef = computed(() => (goldAtYear.value ? '€' + num(goldAtYear.value, 1) + '/g' : 'n/a'))
const wageRef = computed(() => (wageAtYear.value ? '€' + Math.round(wageAtYear.value) + '/mo' : 'n/a'))

// One computed row per room type, recomputed with the slider.
const rows = computed(() =>
  ROOM_ORDER.map((rt) => {
    const area = ROOM_SQM[rt]
    const saleSqm = pickByYear(sale.value.by_type[rt], year.value)?.price_eur_sqm ?? null
    const rentSqm = pickByYear(rent.value.by_type[rt], year.value)?.price_eur_sqm ?? null
    const totalSale = saleSqm != null ? saleSqm * area : null
    const monthlyRent = rentSqm != null ? rentSqm * area : null
    const annualRent = monthlyRent != null ? monthlyRent * 12 : null
    const grossYield = totalSale && annualRent ? (annualRent / totalSale) * 100 : null
    const ptr = totalSale && annualRent ? totalSale / annualRent : null
    const costGoldKg = totalSale && goldAtYear.value ? totalSale / goldAtYear.value / 1000 : null
    const minSalaries = totalSale && wageAtYear.value ? totalSale / wageAtYear.value : null
    const fairPrice = annualRent != null ? annualRent * HEALTHY_PTR : null
    const fairCostGoldKg = fairPrice && goldAtYear.value ? fairPrice / goldAtYear.value / 1000 : null
    const fairMinSalaries = fairPrice && wageAtYear.value ? fairPrice / wageAtYear.value : null
    return {
      rt, labelKey: ROOM_LABEL_KEY[rt], area, totalSale, monthlyRent,
      grossYield, ptr, verdict: ptrVerdict(ptr), costGoldKg, minSalaries,
      fairPrice, fairCostGoldKg, fairMinSalaries,
    }
  }),
)

// Representative property for the mortgage panel = 2-room.
const repRow = computed(() => rows.value.find((r) => r.rt === 'двустаен') || rows.value[0])
const mort = computed(() => {
  const price = repRow.value?.totalSale
  if (!price) return null
  const down = price * mortgage.downPct / 100
  const loan = price - down
  const monthly = monthlyPayment(loan, mortgage.ratePct, mortgage.term)
  return { price, down, loan, monthly, minIncome: monthly / 0.5 }
})

const isLatest = computed(() => year.value === MAX)
</script>

<template>
  <div class="dd">
    <!-- Top bar -->
    <header class="dd__top">
      <div class="dd__left">
        <AppLink :to="`/c/${city}`" class="dd__back label">{{ $t('neighbourhood.back') }}</AppLink>
        <div class="dd__title">
          <span class="dd__kicker label">{{ $t('neighbourhood.deepDive') }}</span>
          <h1 class="dd__name display">{{ meta?.name || '…' }}</h1>
        </div>
      </div>

      <div class="dd__year">
        <span class="dd__yval mono">{{ year }}</span>
        <input class="dd__slider" type="range" :min="MIN" :max="MAX" v-model.number="year" />
        <button class="dd__latest label" :class="{ 'dd__latest--on': isLatest }" @click="year = MAX">{{ $t('neighbourhood.latest') }}</button>
      </div>

      <div class="dd__right"></div>
    </header>

    <div v-if="state.loading" class="dd__status label">{{ $t('neighbourhood.loading') }}</div>
    <div v-else-if="state.error" class="dd__status dd__status--err label">{{ state.error }}</div>

    <div v-else class="dd__grid">
      <!-- Cluster -->
      <section class="card card--cluster">
        <div class="card__head label">{{ $t('neighbourhood.ringTitle', { year }) }}</div>
        <!-- Mobile gets a full-width square canvas (CSS aspect-ratio) so the
             ring + labels stay big and readable; desktop keeps the 380px strip. -->
        <div class="dd__ring">
          <BubbleCluster
            :nodes="clusterNodes"
            mode="directional"
            :radius-range="isMobile ? [24, 52] : null"
            :link-prefix="linkPrefix"
            :zoomable="false"
          />
        </div>
        <div class="card__note mono">{{ $t('neighbourhood.ringNote') }}</div>
      </section>

      <!-- Stats (deferred) -->
      <section class="card card--stats">
        <div class="card__head label">
          {{ $t('neighbourhood.airTitle') }}
          <span v-if="air" class="air__yr mono">{{ air.year }}</span>
        </div>
        <table v-if="air" class="air">
          <thead>
            <tr>
              <th></th>
              <th class="mono">PM2.5</th>
              <th class="mono">AQI</th>
            </tr>
          </thead>
          <tbody>
            <tr class="air__row air__row--winter">
              <td class="air__season label">{{ $t('season.winter') }}</td>
              <td class="mono">{{ fmtPm(air.winter?.pm25) }} <span class="air__u">µg/m³</span></td>
              <td class="mono">{{ fmtAqi(air.winter?.aqi) }}</td>
            </tr>
            <tr class="air__row air__row--summer">
              <td class="air__season label">{{ $t('season.summer') }}</td>
              <td class="mono">{{ fmtPm(air.summer?.pm25) }} <span class="air__u">µg/m³</span></td>
              <td class="mono">{{ fmtAqi(air.summer?.aqi) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="soon">
          <div class="soon__mark display">◳</div>
          <div class="soon__text label" v-html="$t('neighbourhood.statsSoon')"></div>
        </div>
      </section>

      <!-- Trends -->
      <section class="card">
        <div class="card__head label">{{ $t('neighbourhood.priceHistory') }}</div>
        <PriceChart :series="sale.series" />
      </section>
      <section class="card">
        <div class="card__head label">{{ $t('neighbourhood.rentHistory') }}</div>
        <PriceChart :series="rent.series" />
      </section>

      <!-- Price-to-Rent ratio over time, with verdict bands -->
      <section class="card card--wide">
        <div class="card__head label">{{ $t('neighbourhood.ptrTitle') }}</div>
        <PtrChart :series="ptrSeries" />
        <div class="card__note mono">{{ $t('neighbourhood.ptrNote') }}</div>
      </section>

      <!-- Apartment market table -->
      <section class="card card--wide">
        <div class="card__head label">{{ $t('neighbourhood.marketTitle', { year }) }}</div>
        <div class="tblwrap">
        <table class="tbl mono">
          <thead>
            <tr><th>{{ $t('neighbourhood.table.type') }}</th><th>{{ $t('neighbourhood.table.salePrice') }}</th><th>{{ $t('neighbourhood.table.monthlyRent') }}</th><th>{{ $t('neighbourhood.table.grossYield') }}</th><th>{{ $t('neighbourhood.table.priceRent') }}</th><th class="tbl__verdict">{{ $t('neighbourhood.table.verdict') }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.rt">
              <td class="tbl__lbl">{{ $t(r.labelKey, { sqm: r.area }) }}</td>
              <td>{{ eur(r.totalSale) }}</td>
              <td>{{ eur(r.monthlyRent) }}</td>
              <td>{{ num(r.grossYield) }}%</td>
              <td>{{ num(r.ptr) }}</td>
              <td class="tbl__verdict"><span class="badge" :class="'badge--' + r.verdict.tone">{{ $t(r.verdict.labelKey) }}</span></td>
            </tr>
          </tbody>
        </table>
        </div>
        <div class="card__note mono">{{ $t('neighbourhood.ptrScaleNote') }}</div>
      </section>

      <!-- Affordability — actual -->
      <section class="card card--wide">
        <div class="card__head label">{{ $t('neighbourhood.affordTitle', { year }) }}</div>
        <div class="tblwrap">
        <table class="tbl mono">
          <thead>
            <tr><th>{{ $t('neighbourhood.table.type') }}</th><th>{{ $t('neighbourhood.table.salePrice') }}</th><th>{{ $t('neighbourhood.table.costGold', { rate: goldRef }) }}</th><th>{{ $t('neighbourhood.table.minSalaries', { rate: wageRef }) }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.rt">
              <td class="tbl__lbl">{{ $t(r.labelKey, { sqm: r.area }) }}</td>
              <td>{{ eur(r.totalSale) }}</td>
              <td>{{ r.costGoldKg != null ? num(r.costGoldKg, 2) + ' kg' : '—' }}</td>
              <td>{{ r.minSalaries != null ? Math.round(r.minSalaries).toLocaleString('en-US') : '—' }}</td>
            </tr>
          </tbody>
        </table>
        </div>
      </section>

      <!-- Affordability — healthy benchmark -->
      <section class="card card--wide card--muted">
        <div class="card__head label">{{ $t('neighbourhood.benchTitle', { year }) }}</div>
        <div class="card__lead">{{ $t('neighbourhood.benchLead') }}</div>
        <div class="tblwrap">
        <table class="tbl mono">
          <thead>
            <tr><th>{{ $t('neighbourhood.table.type') }}</th><th>{{ $t('neighbourhood.table.fairPrice') }}</th><th>{{ $t('neighbourhood.table.costGold', { rate: goldRef }) }}</th><th>{{ $t('neighbourhood.table.minSalaries', { rate: wageRef }) }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.rt">
              <td class="tbl__lbl">{{ $t(r.labelKey, { sqm: r.area }) }}</td>
              <td>{{ eur(r.fairPrice) }}</td>
              <td>{{ r.fairCostGoldKg != null ? num(r.fairCostGoldKg, 2) + ' kg' : '—' }}</td>
              <td>{{ r.fairMinSalaries != null ? Math.round(r.fairMinSalaries).toLocaleString('en-US') : '—' }}</td>
            </tr>
          </tbody>
        </table>
        </div>
        <div class="card__note mono" v-html="$t('neighbourhood.benchNote')"></div>
      </section>

      <!-- Mortgage -->
      <section class="card card--wide">
        <div class="card__head label">{{ $t('neighbourhood.mortgageTitle') }}</div>
        <div class="mort">
          <div class="mort__inputs">
            <label class="label">{{ $t('neighbourhood.mort.downPct') }}<input type="number" v-model.number="mortgage.downPct" min="0" max="100" /></label>
            <label class="label">{{ $t('neighbourhood.mort.interestPct') }}<input type="number" step="0.1" v-model.number="mortgage.ratePct" min="0" /></label>
            <label class="label">{{ $t('neighbourhood.mort.termYrs') }}<input type="number" v-model.number="mortgage.term" min="1" max="40" /></label>
          </div>
          <div v-if="mort" class="mort__out">
            <div class="mo"><span class="label">{{ $t('neighbourhood.mort.property') }}</span><b class="mono">{{ eur(mort.price) }}</b></div>
            <div class="mo"><span class="label">{{ $t('neighbourhood.mort.downPayment') }}</span><b class="mono">{{ eur(mort.down) }}</b></div>
            <div class="mo"><span class="label">{{ $t('neighbourhood.mort.loan') }}</span><b class="mono">{{ eur(mort.loan) }}</b></div>
            <div class="mo mo--hl"><span class="label">{{ $t('neighbourhood.mort.monthly') }}</span><b class="mono">{{ eur(mort.monthly) }}</b></div>
            <div class="mo"><span class="label">{{ $t('neighbourhood.mort.minIncome') }}</span><b class="mono">{{ eur(mort.minIncome) }}</b></div>
          </div>
          <div v-else class="card__note mono">{{ $t('neighbourhood.mort.noData') }}</div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.dd { min-height: 100vh; padding: 0 0 60px; }
.dd__top {
  position: sticky; top: 0; z-index: 20;
  display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px;
  background: var(--surface); border-bottom: var(--stroke);
  padding: 12px 24px;
}
.dd__left { display: flex; align-items: center; gap: 16px; }
.dd__back { border: var(--stroke); background: var(--surface); padding: 8px 12px; box-shadow: 3px 3px 0 0 var(--ink); }
.dd__title { display: flex; flex-direction: column; }
.dd__kicker { color: var(--pink); }
.dd__name { font-size: 36px; line-height: 0.9; }
.dd__right {}

.dd__year { justify-self: center; display: flex; align-items: center; gap: 16px; }
.dd__latest { border: var(--stroke); background: var(--surface); padding: 8px 14px; }
.dd__latest--on { background: var(--ink); color: var(--bg); }
.dd__yval {
  min-width: 84px; text-align: center; border: var(--stroke); padding: 8px 12px;
  background: var(--coral); color: #fff; font-size: 24px; font-weight: 700;
  box-shadow: var(--shadow);
}
/* Chunky on-brand range slider, centered + large */
.dd__slider {
  -webkit-appearance: none; appearance: none;
  width: 460px; height: 12px; margin: 0;
  background: var(--bg); border: var(--stroke); cursor: pointer;
}
.dd__slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 24px; height: 24px; background: var(--pink);
  border: var(--stroke); box-shadow: 2px 2px 0 0 var(--ink); cursor: pointer;
}
.dd__slider::-moz-range-thumb {
  width: 24px; height: 24px; background: var(--pink);
  border: var(--stroke); cursor: pointer;
}
@media (max-width: 1100px) { .dd__slider { width: 300px; } }

.dd__status { padding: 40px; text-align: center; }
.dd__status--err { color: var(--pink); }

.dd__grid {
  display: grid; gap: 18px; padding: 24px;
  grid-template-columns: 1fr 1fr;
  max-width: 1200px; margin: 0 auto;
}
.card {
  background: var(--surface); border: var(--stroke); box-shadow: var(--shadow);
  padding: 16px;
}
.card--cluster, .card--wide { grid-column: 1 / -1; }
.dd__ring { height: 380px; }
.card--stats { grid-column: 1 / -1; }
.card--muted { background: var(--surface-muted); }
.card__head { color: #555; margin-bottom: 12px; }
.card__lead { color: #555; font-size: 12px; margin: -4px 0 12px; }
.card__note { font-size: 11px; color: #777; margin-top: 10px; }

.air__yr { font-size: 11px; color: #999; margin-left: 6px; }
.air { width: 100%; border-collapse: collapse; }
.air th, .air td { text-align: right; padding: 8px 10px; border-bottom: 1px solid var(--neutral); }
.air th:first-child, .air td:first-child { text-align: left; }
.air thead th { font-size: 11px; color: #999; }
.air__season { color: #fff; }
.air__row--winter .air__season { background: var(--blue); }
.air__row--summer .air__season { background: var(--coral); }
.air__season { padding: 4px 10px; }
.air__u { color: #999; font-size: 11px; }
.soon { display: flex; align-items: center; gap: 18px; justify-content: center; padding: 18px; color: #aaa; }
.soon__mark { font-size: 44px; color: var(--neutral); }
.soon__text { line-height: 1.6; text-align: center; }
.soon__text :deep(span) { color: var(--pink); }

.tblwrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { border: var(--stroke); padding: 8px 10px; text-align: right; }
.tbl th { background: var(--bg); text-transform: uppercase; font-size: 11px; letter-spacing: 0.06em; }
.tbl th:first-child, .tbl__lbl { text-align: left; }
.tbl__lbl { font-family: var(--font-head); font-weight: 600; }

/* Fixed-width verdict column so the table never reflows as the slider changes labels. */
.tbl__verdict { width: 132px; }
.tbl__verdict .badge { display: block; width: 100%; text-align: center; }

.badge { display: inline-block; padding: 3px 8px; border: 2px solid var(--ink); font-size: 11px; font-weight: 700; text-transform: uppercase; }
.badge--buy { background: #00a89c; color: #fff; }
.badge--good { background: var(--teal); }
.badge--fair { background: #ffd34d; }
.badge--stretched { background: #ffa630; }
.badge--expensive { background: var(--coral); color: #fff; }
.badge--overpriced { background: var(--pink); color: #fff; }
.badge--extreme { background: var(--ink); color: #fff; }
.badge--na { background: var(--neutral); }

.mort { display: flex; gap: 24px; flex-wrap: wrap; }
.mort__inputs { display: flex; flex-direction: column; gap: 10px; min-width: 160px; }
.mort__inputs label { display: flex; flex-direction: column; gap: 4px; color: #555; }
.mort__inputs input { border: var(--stroke); padding: 6px 8px; font-family: var(--font-mono); font-size: 14px; }
.mort__out { flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-content: start; }
.mo { border: var(--stroke); padding: 8px 12px; display: flex; flex-direction: column; gap: 4px; }
.mo span { color: #555; }
.mo b { font-size: 20px; font-family: var(--font-display); }
.mo--hl { background: var(--pink); color: #fff; }
.mo--hl span { color: #ffd; }

/* Mobile: stack the top bar, single-column cards, sideways-scrolling tables. */
@media (max-width: 768px) {
  .dd__top {
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 10px 12px;
    top: var(--mhead-h); /* stick below the fixed mobile header */
  }
  .dd__left { gap: 12px; }
  .dd__name { font-size: 26px; }
  .dd__right { display: none; }
  .dd__year {
    justify-self: stretch;
    gap: 10px;
  }
  .dd__yval { min-width: 64px; font-size: 18px; padding: 7px 8px; }
  .dd__slider { width: auto; flex: 1; min-width: 0; }
  .dd__latest { padding: 8px 10px; }

  .dd__grid {
    grid-template-columns: 1fr;
    gap: 14px;
    padding: 12px;
  }
  .dd__ring {
    height: auto;
    aspect-ratio: 1 / 1;
  }
  .tbl { min-width: 520px; font-size: 12px; }
  .tbl th, .tbl td { padding: 7px 8px; }
  .soon { flex-direction: column; gap: 10px; }
  .mort { flex-direction: column; gap: 16px; }
  .mort__inputs { flex-direction: row; gap: 10px; min-width: 0; }
  .mort__inputs label { flex: 1; min-width: 0; }
  .mort__inputs input { width: 100%; }
  .mo b { font-size: 17px; }
}
</style>
