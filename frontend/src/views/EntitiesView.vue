<script setup>
/* Entity browse — search ANY company, builder, or person in the ownership graph
 * (not just the 134 licensed builders). List-first; the global constellation is a
 * toggle. Click a row to open that entity's page. */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { entityPath } from '../router'
import { useAuthStore } from '../stores/authStore'
import StatTile from '../components/StatTile.vue'
import OwnershipGraph from '../components/OwnershipGraph.vue'
import GraphLegend from '../components/GraphLegend.vue'
import AppLink from '../components/AppLink.vue'
import DisclaimerBanner from '../components/DisclaimerBanner.vue'
import ResearchOrderModal from '../components/ResearchOrderModal.vue'
import { setPageMeta } from '../lib/pageMeta'
import { readGraph, writeGraph } from '../lib/graphCache'

const { t } = useI18n()
const auth = useAuthStore()

const stats = ref(null)
const grandTotal = ref(null)
const showOrderModal = ref(false)

const q = ref('')
const kind = ref('all') // all | builder | company | person
const onlyReports = ref(false) // ⚠ show only entities with public reports
const items = ref([])
const total = ref(0)
const loading = ref(false)

const PAGE = 50
const offset = ref(0)
const hasMore = ref(false)
const loadingMore = ref(false)
const sentinel = ref(null)
let observer = null

const view = ref('list') // 'list' | 'network'
const graph = ref({ nodes: [], edges: [] })
let graphLoaded = false

// The constellation is ~1MB over the wire, so which tab you were on is kept in
// the URL (?view=network) and the payload in sessionStorage — a refresh restores
// both instead of re-fetching. The router parses pathname only (router.js:25),
// so this query param is invisible to it; replaceState keeps it out of history.
const GRAPH_LIMIT = 2000

function syncViewToUrl(v) {
  const url = new URL(window.location.href)
  if (v === 'network') url.searchParams.set('view', 'network')
  else url.searchParams.delete('view')
  history.replaceState(null, '', url.pathname + url.search)
}

function showList() {
  view.value = 'list'
  syncViewToUrl('list')
}

const KINDS = [
  { k: 'all', labelKey: 'entities.kinds.all' },
  { k: 'builder', labelKey: 'entities.kinds.builder' },
  { k: 'company', labelKey: 'entities.kinds.company' },
  { k: 'person', labelKey: 'entities.kinds.person' },
]

let timer = null
async function loadPage() {
  if (loadingMore.value) return
  const first = offset.value === 0
  if (first) loading.value = true
  else loadingMore.value = true
  try {
    const r = await api.entities(q.value.trim(), kind.value, {
      hasSignals: onlyReports.value,
      limit: PAGE,
      offset: offset.value,
    })
    items.value = first ? r.items : items.value.concat(r.items)
    total.value = r.total
    offset.value = items.value.length
    hasMore.value = items.value.length < r.total
    if (grandTotal.value == null && !q.value && kind.value === 'all' && !onlyReports.value)
      grandTotal.value = r.total
  } catch (e) {
    if (first) items.value = []
    hasMore.value = false
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}
function search() {
  offset.value = 0
  items.value = []
  hasMore.value = false
  return loadPage()
}
function onInput() {
  clearTimeout(timer)
  timer = setTimeout(search, 200)
}
watch(kind, search)
watch(onlyReports, search)
// re-attach the scroll sentinel when returning to the list view (v-if recreates it)
watch(sentinel, (el) => { if (observer && el) observer.observe(el) })

async function showNetwork() {
  // The global ownership graph is login-gated (it's the people network).
  if (!auth.isAuthenticated) { auth.openModal(); return }
  view.value = 'network'
  syncViewToUrl('network')
  if (graphLoaded) return
  const cached = readGraph(GRAPH_LIMIT)
  if (cached) {
    graph.value = cached
    graphLoaded = true
    return
  }
  graph.value = await api.graph(GRAPH_LIMIT)
  graphLoaded = true
  writeGraph(GRAPH_LIMIT, graph.value)
}

function badge(it) {
  if (it.is_builder) return { cls: 'builder' }
  return it.kind === 'person' ? { cls: 'person' } : { cls: 'company' }
}

function cautionCount(it) {
  const c = it.signal_counts
  return c ? (c.official + c.community + c.web) : 0
}

onMounted(async () => {
  setPageMeta({
    title: t('meta.entitiesTitle'),
    description: t('meta.entitiesDesc'),
  })
  stats.value = await api.stats().catch(() => null)
  await search()
  // Restore the constellation on refresh. `isAuthenticated` is the token from
  // localStorage, so it is already truthy here — no need to await auth.ready.
  // A stale token still 401s, so fall back to the list rather than throwing out
  // of onMounted (which would leave the observer below unattached).
  if (view.value === 'list'
      && new URLSearchParams(window.location.search).get('view') === 'network'
      && auth.isAuthenticated) {
    await showNetwork().catch(() => { showList() })
  }
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && view.value === 'list'
        && hasMore.value && !loading.value && !loadingMore.value) {
      loadPage()
    }
  }, { rootMargin: '200px' })
  if (sentinel.value) observer.observe(sentinel.value)
})

onBeforeUnmount(() => observer && observer.disconnect())
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h1 class="display">{{ $t('entities.title') }}</h1>
        <p class="lede">{{ $t('entities.lede') }}</p>
      </div>
      <div class="seg">
        <button :class="{ on: view === 'list' }" @click="showList">{{ $t('entities.list') }}</button>
        <button :class="{ on: view === 'network' }" @click="showNetwork">{{ $t('entities.network') }}</button>
      </div>
    </header>

    <DisclaimerBanner />

    <div class="stats">
      <StatTile :label="$t('entities.stats.docsScanned')" :value="stats ? $t('entities.docsValue', { n: (Math.round(stats.data_scanned_bytes / 3000 / 100) * 100).toLocaleString() }) : '—'" accent="var(--coral)" />
      <StatTile :label="$t('entities.stats.licensedBuilders')" :value="stats ? String(stats.builders) : '—'" accent="var(--pink)" />
      <StatTile :label="$t('entities.stats.entitiesGraph')" :value="grandTotal != null ? String(grandTotal) : '—'" accent="var(--blue)" />
      <StatTile :label="$t('entities.stats.projects')" :value="stats ? String(stats.projects) : '—'" accent="var(--teal)" />
    </div>

    <!-- LIST -->
    <section v-if="view === 'list'" class="browse">
      <div class="controls">
        <input
          class="search mono"
          v-model="q"
          @input="onInput"
          :placeholder="$t('entities.searchPlaceholder')"
        />
        <div class="kinds">
          <button
            v-for="kk in KINDS"
            :key="kk.k"
            class="kind label"
            :class="{ on: kind === kk.k }"
            @click="kind = kk.k"
          >{{ $t(kk.labelKey) }}</button>
        </div>
        <button
          v-if="auth.isAuthenticated"
          class="kind label reports-toggle"
          :class="{ on: onlyReports }"
          @click="onlyReports = !onlyReports"
          :title="$t('entities.reportsTitleAuth')"
        >{{ $t('entities.reports') }}</button>
        <button
          v-else
          class="kind label reports-toggle"
          @click="auth.openModal()"
          :title="$t('entities.reportsTitleAnon')"
        >{{ $t('entities.reports') }}</button>
      </div>

      <div class="count mono">{{ loading ? $t('entities.searching') : (total === 1 ? $t('entities.resultOne', { n: total }) : $t('entities.resultMany', { n: total })) }}</div>

      <ul class="rows">
        <li v-for="it in items" :key="it.id" class="row">
          <AppLink :to="entityPath(it.key, it.slug)" class="row__link">
            <span class="bdg" :class="badge(it).cls">{{ $t('entities.badge.' + badge(it).cls) }}</span>
            <span class="warncell">
              <span v-if="cautionCount(it)" class="warnchip" :title="$t('entities.reportChip', { n: cautionCount(it) })">⚠ {{ cautionCount(it) }}</span>
            </span>
            <span class="rname">{{ it.name }}</span>
            <span v-if="it.status" class="rstatus label">{{ it.status }}</span>
            <span class="reik mono">{{ it.eik || '—' }}</span>
            <span class="rdeg mono" :title="$t('entities.connections', { n: it.degree })">{{ it.degree }} ↔</span>
          </AppLink>
        </li>
        <li v-if="hasMore" ref="sentinel" class="sentinel mono">{{ loadingMore ? $t('entities.loadingMore') : '' }}</li>
      </ul>
      <div v-if="!loading && !items.length" class="empty">
        <p class="label">{{ q ? $t('entities.noMatchesFor', { q }) : $t('entities.noMatches') }}</p>
        <p class="empty-sub">{{ $t('entities.orderPrompt') }}</p>
        <button class="order-cta" @click="showOrderModal = true">{{ $t('entities.orderCta') }}</button>
      </div>
    </section>

    <!-- NETWORK -->
    <section v-else class="net">
      <OwnershipGraph
        :nodes="graph.nodes" :edges="graph.edges" :height="620"
        :layout-key="`global:${GRAPH_LIMIT}`" />
      <div class="legend-wrap"><GraphLegend /></div>
    </section>

    <ResearchOrderModal
      v-if="showOrderModal"
      :initial-company="q"
      :initial-query="q"
      @close="showOrderModal = false"
    />
  </div>
</template>

<style scoped>
.page { padding: 22px 24px 40px; max-width: 1100px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.head h1 { font-size: 38px; line-height: 0.92; }
.lede { margin: 6px 0 0; font-size: 14px; color: #444; max-width: 560px; }

.seg { display: inline-flex; border: var(--stroke); box-shadow: var(--shadow); flex: none; }
.seg button { border: none; border-right: var(--stroke); background: var(--surface); padding: 8px 16px; font-weight: 800; font-family: var(--font-display); cursor: pointer; }
.seg button:last-child { border-right: none; }
.seg button.on { background: var(--pink); color: #fff; }

.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 18px 0; }

.controls { display: flex; gap: 14px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.search { flex: 1; min-width: 260px; border: var(--stroke); box-shadow: var(--shadow); padding: 11px 12px; font-size: 14px; background: var(--surface); }
.search:focus { outline: none; box-shadow: var(--shadow), 0 0 0 3px var(--pink); }
.kinds { display: inline-flex; border: var(--stroke); box-shadow: var(--shadow); }
.kind { border: none; border-right: var(--stroke); background: var(--surface); padding: 9px 14px; cursor: pointer; }
.kind:last-child { border-right: none; }
.kind.on { background: var(--ink); color: var(--bg); }

.reports-toggle { border: var(--stroke); box-shadow: var(--shadow); white-space: nowrap; }
.reports-toggle.on { background: #FF6B47; color: #fff; }
.locked-toggle { background: var(--surface); cursor: pointer; }
.locked-toggle:active { transform: translate(1px, 1px); }

.count { font-size: 12px; color: #666; margin-bottom: 8px; }

.sentinel { border: var(--stroke); border-top: none; background: var(--surface); padding: 10px 14px; text-align: center; font-size: 12px; color: #888; }

.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.row {
  display: grid; grid-template-columns: 96px 52px 1fr auto auto auto;
  align-items: center; gap: 14px;
  border: var(--stroke); border-bottom: none; background: var(--surface);
  padding: 11px 14px; cursor: pointer;
}
.row:last-child { border-bottom: var(--stroke); }
.row:hover { background: var(--bg); }
.row__link { display: contents; color: inherit; text-decoration: none; }
.bdg { border: var(--stroke); text-align: center; font-size: 10px; font-weight: 800; text-transform: uppercase; padding: 3px 0; }
.bdg.builder { background: var(--pink); color: #fff; }
.bdg.company { background: var(--blue); color: #fff; }
.bdg.person { background: var(--coral); color: #fff; }
.warncell { display: flex; justify-content: center; }
.warnchip { border: 2px solid var(--ink); background: #FF6B47; color: #fff; font-size: 10px; font-weight: 800; padding: 2px 5px; white-space: nowrap; }
.rname { font-family: var(--font-head); font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rstatus { font-size: 10px; color: #666; border: var(--stroke); padding: 2px 6px; }
.reik { font-size: 12px; color: #666; }
.rdeg { font-size: 12px; font-weight: 700; min-width: 48px; text-align: right; }
.empty { padding: 30px; text-align: center; color: #888; }
.empty-sub { margin: 8px 0 16px; font-size: 13px; color: #555; }
.order-cta {
  border: var(--stroke); background: var(--pink); color: #fff; box-shadow: var(--shadow);
  padding: 11px 22px; font-weight: 800; font-family: var(--font-display);
  text-transform: uppercase; cursor: pointer;
}
.order-cta:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }

.net { position: relative; margin-top: 8px; }
.legend-wrap { position: absolute; left: 14px; bottom: 14px; }

/* Mobile: stacked header, 2×2 stat tiles, list rows reflow to two lines
   (name on top, badge/status/ЕИК/degree as a chip row underneath). */
@media (max-width: 768px) {
  .page { padding: 14px 12px 40px; }
  .head { flex-direction: column; gap: 12px; }
  .head h1 { font-size: 30px; }
  .stats { grid-template-columns: 1fr 1fr; gap: 10px; }
  .controls { gap: 10px; }
  .search { flex: 1 1 100%; min-width: 0; }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
    padding: 10px 12px;
  }
  .rname {
    order: -1;
    width: 100%;
    white-space: normal;
  }
  .bdg { padding: 3px 8px; }
  .rdeg { margin-left: auto; min-width: 0; }
  .legend-wrap { position: static; margin-top: 10px; }
}
</style>
