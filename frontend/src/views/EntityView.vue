<script setup>
/* Single entity (company / builder / person): profile sidebar left, ego network right. */
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { goBack, entityPath } from '../router'
import { useAuthStore } from '../stores/authStore'
import OwnershipGraph from '../components/OwnershipGraph.vue'
import GraphLegend from '../components/GraphLegend.vue'
import CourtResearchModal from '../components/CourtResearchModal.vue'
import AppLink from '../components/AppLink.vue'
import { setPageMeta } from '../lib/pageMeta'
import { useIsMobile } from '../lib/useIsMobile'

const props = defineProps({ ekey: String })
const { t } = useI18n()
const auth = useAuthStore()
const isMobile = useIsMobile()

const profile = ref(null)
const net = ref({ nodes: [], edges: [], center: null })
const depth = ref(2)
const loading = ref(true)
const error = ref(null)
const showOrderModal = ref(false)

// Order research: members open the modal; anonymous viewers get the sign-in prompt.
function openOrder() {
  if (auth.isAuthenticated) showOrderModal.value = true
  else auth.openModal()
}

const winHeight = ref(window.innerHeight)
function onResize() { winHeight.value = window.innerHeight }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))
// Mobile stacks panel + graph in one scrolling column, so cap the graph height.
const graphHeight = computed(() =>
  isMobile.value ? Math.min(480, winHeight.value - 140) : winHeight.value - 64)

const capital = computed(() => {
  const v = profile.value?.capital_bgn
  return v != null ? new Intl.NumberFormat('bg-BG').format(Math.round(v)) + ' лв.' : '—'
})
const kindLabel = computed(() => {
  const p = profile.value
  if (!p) return ''
  if (p.is_builder) return t('entity.kind.builder')
  return p.kind === 'person' ? t('entity.kind.person') : t('entity.kind.company')
})

async function load() {
  loading.value = true
  error.value = null
  try {
    // The network endpoint 401s for anonymous viewers, so only fetch it when
    // signed in; the profile itself is public (owner/research fields stripped).
    profile.value = await api.entity(props.ekey)
    const eikStr = profile.value.eik ? ` (${t('entity.eik')} ${profile.value.eik})` : ''
    setPageMeta({
      title: t('meta.entityTitle', { name: profile.value.name }),
      description: t('meta.entityDesc', { name: profile.value.name, eik: eikStr }),
    })
    net.value = auth.isAuthenticated
      ? await api.entityNetwork(props.ekey, depth.value)
      : { nodes: [], edges: [], center: null }
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}
async function reloadNetwork() {
  if (auth.isAuthenticated) net.value = await api.entityNetwork(props.ekey, depth.value)
}

watch(() => props.ekey, load, { immediate: true })
watch(depth, reloadNetwork)
// Signing in (or out) reveals/hides the locked data — refetch this entity.
watch(() => auth.isAuthenticated, load)

// --- problematic-developer signals (evidence aggregator, NOT a verdict) ---
const TIER_META = {
  official: { labelKey: 'entity.tier.official', cls: 'official', noteKey: 'entity.tier.officialNote' },
  community: { labelKey: 'entity.tier.community', cls: 'community', noteKey: 'entity.tier.communityNote' },
  web: { labelKey: 'entity.tier.web', cls: 'web', noteKey: 'entity.tier.webNote' },
}
const signalCounts = computed(() => profile.value?.signal_counts || { official: 0, community: 0, web: 0 })
const totalSignals = computed(() =>
  Object.values(signalCounts.value).reduce((a, b) => a + b, 0))
const signalGroups = computed(() => {
  const sigs = profile.value?.signals || []
  return ['official', 'community', 'web']
    .map((tier) => ({ tier, ...TIER_META[tier], items: sigs.filter((s) => s.tier === tier) }))
    .filter((g) => g.items.length)
})

// owners (in/ownership), managers (in/management), owns (out/ownership), manages (out/management)
const sections = computed(() => {
  const p = profile.value
  if (!p) return []
  return [
    { titleKey: 'entity.sections.owners', list: p.owners, kindHint: null },
    { titleKey: 'entity.sections.managers', list: p.managers, kindHint: 'person' },
    { titleKey: 'entity.sections.owns', list: p.owns, kindHint: null },
    { titleKey: 'entity.sections.manages', list: p.manages, kindHint: null },
  ].filter((s) => s.list && s.list.length)
})
</script>

<template>
  <div class="page">
    <header class="topbar">
      <button class="ghost" @click="goBack('/entities')">{{ $t('entity.browse') }}</button>
      <div class="mono tag">{{ $t('entity.ownershipTag') }}</div>
      <AppLink v-if="profile" :to="entityPath(ekey, profile.slug, '/network')" class="ghost net-btn">{{ $t('entity.network') }}</AppLink>
      <AppLink v-if="auth.user?.is_superuser && profile && profile.kind === 'company'" :to="`/certificate/${profile.eik || ekey}`" class="ghost cert-btn">Сертификат за прозрачност</AppLink>
    </header>

    <div v-if="error" class="banner">{{ error }}</div>

    <div class="grid" v-if="profile">
      <aside class="panel">
        <h1 class="display name">{{ profile.name }}</h1>
        <div class="mono sub">
          {{ kindLabel }}<template v-if="profile.eik"> · {{ $t('entity.eik') }} {{ profile.eik }}</template>
          <template v-if="profile.legal_form"> · {{ profile.legal_form }}</template>
        </div>

        <div class="pills">
          <span v-if="profile.status" class="pill" :class="profile.status === 'Активен' || profile.status === 'active' ? 'ok' : 'mut'">
            {{ profile.status }}
          </span>
          <span v-if="profile.ksb_category" class="pill blue">КСБ {{ profile.ksb_category }}</span>
          <span v-if="profile.has_seizure" class="pill danger">{{ $t('entity.seizurePill') }}</span>
          <span v-if="profile.insolvency_flag" class="pill warn">{{ $t('entity.insolvency') }}</span>
          <span v-if="profile.tax_debt_bgn" class="pill warn">{{ $t('entity.taxDebt') }}</span>
          <span v-if="totalSignals" class="pill caution">{{ totalSignals > 1 ? $t('entity.reportsPillMany', { n: totalSignals }) : $t('entity.reportsPillOne', { n: totalSignals }) }}</span>
        </div>

        <button v-if="profile.kind === 'company'" class="orderbtn" @click="openOrder">
          {{ $t('courtOrder.button') }}
        </button>

        <dl v-if="profile.kind === 'company'" class="facts">
          <div><dt>{{ $t('entity.capital') }}</dt><dd class="mono">{{ capital }}</dd></div>
          <div><dt>{{ $t('entity.address') }}</dt><dd class="mono">{{ profile.address || '—' }}</dd></div>
        </dl>

        <!-- запор върху дружествен дял. Its own card rather than a row in the
             signals feed: it is official-tier, and materially heavier than a
             forum mention or a news hit. Gated with the rest of the research
             fields, so it simply is not present for anonymous viewers. -->
        <section v-if="profile.has_seizure" class="seizure">
          <h2 class="display sec danger">{{ $t('entity.seizureTitle') }}</h2>
          <p class="seizure__lead">
            {{ profile.seizure_count > 1
                ? $t('entity.seizureLeadMany', { n: profile.seizure_count })
                : $t('entity.seizureLeadOne') }}
            <span v-if="profile.seizure_last_at" class="mono seizure__date">
              · {{ profile.seizure_last_at }}
            </span>
          </p>
          <p class="seizure__note">{{ $t('entity.seizureNote') }}</p>
          <a v-if="profile.seizure_source_url" :href="profile.seizure_source_url"
             target="_blank" rel="noopener" class="seizure__src">
            {{ $t('entity.seizureSource') }}
          </a>
        </section>

        <!-- Locked: owners/managers/network/reports are gated behind login. -->
        <section v-if="!auth.isAuthenticated" class="lockcard">
          <h2 class="display sec">{{ $t('entity.lockedTitle') }}</h2>
          <p class="lockmsg">{{ $t('entity.lockedMsg') }}</p>
          <button class="lockbtn" @click="auth.openModal()">{{ $t('common.signInUnlock') }}</button>
        </section>

        <section v-for="s in sections" :key="s.titleKey">
          <h2 class="display sec">{{ $t(s.titleKey) }}</h2>
          <ul class="people">
            <li v-for="(o, i) in s.list" :key="s.titleKey + i" :class="{ link: o.key }">
              <AppLink v-if="o.key" :to="entityPath(o.key, o.slug)" class="people__link">
                <span class="dot" :class="o.is_builder ? 'builder' : o.kind"></span>
                <span class="pname">{{ o.name }}</span>
                <span v-if="o.share_pct != null" class="share">{{ Math.round(o.share_pct) }}%</span>
                <span v-else-if="o.role" class="role">{{ o.role }}</span>
                <span v-if="!o.is_current" class="bivsh">{{ $t('entity.former') }}</span>
              </AppLink>
              <template v-else>
                <span class="dot" :class="o.is_builder ? 'builder' : o.kind"></span>
                <span class="pname">{{ o.name }}</span>
                <span v-if="o.share_pct != null" class="share">{{ Math.round(o.share_pct) }}%</span>
                <span v-else-if="o.role" class="role">{{ o.role }}</span>
                <span v-if="!o.is_current" class="bivsh">{{ $t('entity.former') }}</span>
              </template>
            </li>
          </ul>
        </section>

        <section v-if="profile.projects && profile.projects.length">
          <h2 class="display sec">{{ $t('entity.projects') }}</h2>
          <ul class="projects">
            <li v-for="(pr, i) in profile.projects" :key="'p' + i">
              <span class="pname">{{ pr.name }}</span>
              <span class="mono small">{{ pr.akt_stage || '' }} {{ pr.price_eur_sqm ? '· €' + Math.round(pr.price_eur_sqm) + '/м²' : '' }}</span>
            </li>
          </ul>
        </section>

        <div v-if="!sections.length && !(profile.projects && profile.projects.length)" class="noconn label">
          {{ $t('entity.noConnections') }}
        </div>

        <!-- Evidence aggregator: public reports/records about this developer.
             Shown last — after ownership/management — sources + dates, never our verdict. -->
        <section v-if="totalSignals" class="signals">
          <h2 class="display sec warned">{{ $t('entity.reportsTitle') }}</h2>
          <p class="disclaimer mono">{{ $t('entity.reportsDisclaimer') }}</p>
          <div v-for="g in signalGroups" :key="g.tier" class="sgroup">
            <div class="sgroup-head" :class="g.cls">
              {{ $t(g.labelKey) }} <span class="sgroup-note">· {{ $t(g.noteKey) }}</span>
            </div>
            <ul class="evidence">
              <li v-for="(s, i) in g.items" :key="g.tier + i">
                <a :href="s.url" target="_blank" rel="noopener" class="etitle">
                  {{ s.title || s.matched_name }}
                </a>
                <div class="emeta mono">
                  <span v-if="s.source_site">{{ s.source_site }}</span>
                  <span v-if="s.observed_date">· {{ s.observed_date }}</span>
                  <span v-if="s.subject !== 'self'" class="via">· {{ $t('entity.via') }} {{ s.subject }}</span>
                </div>
                <p v-if="s.snippet" class="esnip">“{{ s.snippet }}”</p>
              </li>
            </ul>
          </div>
        </section>
      </aside>

      <main class="canvas">
        <template v-if="auth.isAuthenticated">
          <div class="toolbar">
            <span class="label">{{ $t('entity.depth') }}</span>
            <div class="seg">
              <button v-for="d in [1, 2, 3]" :key="d" :class="{ on: depth === d }" @click="depth = d">{{ d }}</button>
            </div>
            <span class="mono count">{{ $t('entity.nodesLinks', { nodes: net.nodes.length, links: net.edges.length }) }}</span>
          </div>
          <OwnershipGraph :nodes="net.nodes" :edges="net.edges" :center-id="net.center" :height="graphHeight" />
          <div class="legend-wrap"><GraphLegend /></div>
        </template>
        <div v-else class="canvas-lock">
          <div class="lockpanel">
            <div class="display lockbig">🔒</div>
            <h2 class="display">{{ $t('entity.networkLocked') }}</h2>
            <p class="lockmsg">{{ $t('entity.networkLockedMsg') }}</p>
            <button class="lockbtn" @click="auth.openModal()">{{ $t('common.signInUnlock') }}</button>
          </div>
        </div>
      </main>
    </div>

    <div v-else-if="loading" class="loading display">{{ $t('entity.loading') }}</div>

    <CourtResearchModal
      v-if="showOrderModal && profile"
      :ekey="ekey"
      :profile="profile"
      :nodes="net.nodes"
      :depth="depth"
      @close="showOrderModal = false"
    />
  </div>
</template>

<style scoped>
.page { height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
.topbar {
  display: flex; align-items: center; gap: 16px;
  padding: 14px 24px; border-bottom: var(--stroke-thick); background: var(--surface);
}
.tag { font-size: 11px; color: #555; }
.net-btn { margin-left: auto; }
.cert-btn { background: var(--teal); }
.ghost {
  border: var(--stroke); background: var(--surface); box-shadow: var(--shadow);
  padding: 6px 12px; font-weight: 700; cursor: pointer;
}
.ghost:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.banner { margin: 16px 24px; border: var(--stroke); background: var(--pink); color: #fff; padding: 10px; }

.grid { display: grid; grid-template-columns: var(--panel-w) 1fr; gap: 20px; padding: 20px 24px; flex: 1; min-height: 0; align-items: start; overflow: hidden; }
.panel { border: var(--stroke); background: var(--surface); box-shadow: var(--shadow-lg); padding: 18px; overflow-y: auto; height: 100%; box-sizing: border-box; }
.canvas { position: relative; }
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.seg { display: inline-flex; border: var(--stroke); box-shadow: var(--shadow); }
.seg button { border: none; border-right: var(--stroke); background: var(--surface); padding: 5px 13px; font-weight: 800; font-family: var(--font-display); cursor: pointer; }
.seg button:last-child { border-right: none; }
.seg button.on { background: var(--pink); color: #fff; }
.count { font-size: 12px; color: #555; margin-left: auto; }
.legend-wrap { position: absolute; right: 14px; bottom: 14px; }
.name { font-size: 30px; line-height: 0.95; }
.sub { font-size: 12px; color: #555; margin-top: 6px; }

.pills { display: flex; flex-wrap: wrap; gap: 6px; margin: 14px 0; }
.pill { border: var(--stroke); padding: 3px 9px; font-weight: 700; font-size: 11px; text-transform: uppercase; }
.pill.ok { background: var(--teal); }
.pill.blue { background: var(--blue); color: #fff; }
.pill.warn { background: var(--pink); color: #fff; }
.pill.danger { background: #b1121c; color: #fff; }
.seizure {
  margin: 18px 0; padding: 14px;
  border: var(--stroke); border-left: 8px solid #b1121c;
  box-shadow: var(--shadow); background: #FFF1F1;
}
.seizure .sec.danger { color: #b1121c; border-bottom-color: #b1121c; margin-top: 0; }
.seizure__lead { font-weight: 700; margin: 6px 0; }
.seizure__date { font-weight: 400; opacity: .75; }
.seizure__note { font-size: 13px; line-height: 1.5; margin: 8px 0 12px; }
.seizure__src {
  display: inline-block; font-weight: 700; text-decoration: underline;
  color: #b1121c;
}
.pill.mut { background: var(--neutral); }
.pill.caution { background: #FF6B47; color: #fff; }

.orderbtn {
  display: block; width: 100%; margin: 0 0 4px;
  border: var(--stroke); background: var(--pink); color: #fff; box-shadow: var(--shadow);
  padding: 10px 12px; font-weight: 800; font-family: var(--font-display);
  text-transform: uppercase; cursor: pointer;
}
.orderbtn:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }

/* evidence aggregator */
.signals { margin: 18px 0; border: var(--stroke); box-shadow: var(--shadow); padding: 12px; background: #FFF8EC; }
.sec.warned { color: #b22; border-bottom-color: #b22; margin-top: 0; }
.disclaimer { font-size: 10px; color: #777; margin: 0 0 12px; line-height: 1.4; }
.sgroup { margin-bottom: 12px; }
.sgroup-head { font-weight: 800; font-size: 11px; text-transform: uppercase; padding: 3px 7px; border: var(--stroke); display: inline-block; }
.sgroup-head.official { background: var(--pink); color: #fff; }
.sgroup-head.community { background: #FF6B47; color: #fff; }
.sgroup-head.web { background: var(--neutral); }
.sgroup-note { font-weight: 600; text-transform: none; }
.evidence { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 9px; }
.evidence li { border-left: 3px solid var(--ink); padding-left: 8px; }
.etitle { font-weight: 700; font-size: 13px; color: var(--ink); text-decoration: underline; }
.emeta { font-size: 10px; color: #777; margin-top: 2px; display: flex; gap: 5px; flex-wrap: wrap; }
.emeta .via { color: #b22; font-weight: 700; }
.esnip { font-size: 12px; color: #444; margin: 4px 0 0; font-style: italic; }

.facts { display: grid; gap: 8px; margin: 14px 0; }
.facts dt { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: #777; }
.facts dd { margin: 2px 0 0; font-size: 13px; }

.sec { font-size: 16px; margin: 18px 0 8px; border-bottom: var(--stroke); padding-bottom: 4px; }
.people, .projects { list-style: none; margin: 0; padding: 0; display: grid; gap: 7px; }
.people li { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 2px 0; }
.people li.link { cursor: pointer; }
.people li.link:hover .pname { text-decoration: underline; }
.people__link { display: contents; color: inherit; text-decoration: none; }
.dot { width: 11px; height: 11px; border: 2px solid var(--ink); border-radius: 50%; flex: none; }
.dot.builder { background: var(--pink); }
.dot.company { background: var(--blue); }
.dot.person { background: var(--coral); }
.pname { font-weight: 600; }
.share { margin-left: auto; font-family: var(--font-display); font-weight: 800; border: var(--stroke); padding: 0 6px; font-size: 12px; }
.role { margin-left: auto; font-size: 11px; color: #666; font-family: var(--font-mono); }
.bivsh { font-size: 10px; color: #999; text-transform: uppercase; }
.projects li { display: flex; flex-direction: column; gap: 2px; border-left: 3px solid var(--coral); padding-left: 8px; }
.small { font-size: 11px; color: #666; }
.noconn { color: #999; padding: 14px 0; }

.loading { padding: 60px; font-size: 24px; }

/* lock CTAs (anonymous viewers) */
.lockcard { margin: 18px 0; border: var(--stroke); box-shadow: var(--shadow); padding: 14px; background: #FFF8EC; }
.lockcard .sec { margin-top: 0; }
.lockmsg { font-size: 13px; color: #555; margin: 8px 0 12px; line-height: 1.45; }
.lockbtn {
  border: var(--stroke); background: var(--pink); color: #fff; box-shadow: var(--shadow);
  padding: 9px 14px; font-weight: 800; font-family: var(--font-display); text-transform: uppercase; cursor: pointer;
}
.lockbtn:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.canvas-lock { display: flex; align-items: center; justify-content: center; height: 100%; border: var(--stroke); background: var(--surface); box-shadow: var(--shadow-lg); }
.lockpanel { text-align: center; max-width: 320px; padding: 24px; }
.lockbig { font-size: 48px; line-height: 1; }
.lockpanel h2 { font-size: 24px; margin: 8px 0; }

/* Mobile: profile panel on top, network below, one page-level scroll. */
@media (max-width: 768px) {
  .page { height: auto; overflow: visible; }
  .topbar { flex-wrap: wrap; gap: 10px; padding: 10px 12px; }
  .grid {
    grid-template-columns: 1fr;
    gap: 14px;
    padding: 12px;
    height: auto;
    overflow: visible;
  }
  .panel { height: auto; overflow: visible; }
  .name { font-size: 24px; }
  .toolbar { flex-wrap: wrap; }
  .legend-wrap { position: static; margin-top: 10px; }
  .canvas-lock { height: auto; padding: 36px 12px; }
}
</style>
