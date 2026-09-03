<script setup>
// Location Score — paste lat/lng, fetch nearby POIs from Overpass (OSM),
// and grade the spot on transport / shopping / health+education / lifestyle.
// All logic lives in lib/locationScore.js; this file is presentation + state.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { parseCoords, fetchPois, scores, overallScore, groupPois } from '../lib/locationScore'
import { setPageMeta } from '../lib/pageMeta'

const { t } = useI18n()

onMounted(() => setPageMeta({
  title: t('meta.locationTitle'),
  description: t('meta.locationDesc'),
}))

const input = ref('')
const loading = ref(false)
const error = ref('')
const pois = ref(null) // null = nothing analysed yet; [] = analysed, none found

const cardScores = computed(() => (pois.value ? scores(pois.value) : []))
const overall = computed(() => (pois.value?.length ? overallScore(pois.value) : 0))
const groups = computed(() => (pois.value ? groupPois(pois.value) : []))
const hasResults = computed(() => pois.value?.length > 0)

// 0–100 → accent colour (red → coral → teal as the score climbs).
function accentFor(value) {
  if (value >= 70) return 'var(--teal)'
  if (value >= 40) return 'var(--coral)'
  return 'var(--pink)'
}

function gradeFor(value) {
  if (value >= 80) return t('location.grade.excellent')
  if (value >= 60) return t('location.grade.good')
  if (value >= 40) return t('location.grade.fair')
  if (value >= 20) return t('location.grade.poor')
  return t('location.grade.veryPoor')
}

function walkMin(distance) {
  return Math.max(1, Math.round(distance / 80))
}

async function analyze() {
  error.value = ''
  const coords = parseCoords(input.value)
  if (!coords) {
    error.value = t('location.invalidCoords')
    pois.value = null
    return
  }
  loading.value = true
  pois.value = null
  try {
    pois.value = await fetchPois(coords.lat, coords.lon)
  } catch (e) {
    error.value = t('location.overpassError')
    pois.value = null
  } finally {
    loading.value = false
  }
}

function useExample() {
  input.value = '42.6975, 23.3242' // central Sofia
  analyze()
}
</script>

<template>
  <div class="loc">
    <!-- header -->
    <header class="loc__head">
      <h1 class="loc__title display">{{ $t('location.title') }}</h1>
      <p class="loc__sub label">{{ $t('location.subtitle') }}</p>
    </header>

    <!-- input -->
    <div class="loc__bar">
      <input
        v-model="input"
        class="loc__input mono"
        type="text"
        :placeholder="$t('location.placeholder')"
        @keyup.enter="analyze"
      />
      <button class="loc__go label" :disabled="loading" @click="analyze">
        {{ loading ? $t('location.analyzing') : $t('location.analyze') }}
      </button>
    </div>

    <div class="loc__hint label">
      {{ $t('location.hint') }}
      <button class="loc__example" @click="useExample">{{ $t('location.tryExample') }}</button>
    </div>

    <!-- error -->
    <div v-if="error" class="loc__error label">{{ error }}</div>

    <!-- loading -->
    <div v-if="loading" class="loc__loading mono">{{ $t('location.querying') }}</div>

    <!-- empty result -->
    <div v-if="pois && !hasResults && !loading" class="loc__error label">
      {{ $t('location.noPois') }}
    </div>

    <!-- results -->
    <template v-if="hasResults && !loading">
      <!-- overall -->
      <div class="loc__overall" :style="{ '--accent': accentFor(overall) }">
        <div class="loc__overall-meta">
          <div class="loc__overall-label label">{{ $t('location.overall') }}</div>
          <div class="loc__overall-grade label">{{ gradeFor(overall) }}</div>
        </div>
        <div class="loc__overall-num display">{{ overall }}</div>
        <div class="loc__overall-bar">
          <div class="loc__overall-fill" :style="{ width: overall + '%' }"></div>
        </div>
      </div>

      <!-- sub-scores -->
      <div class="loc__tiles">
        <div
          v-for="s in cardScores"
          :key="s.key"
          class="tile"
          :style="{ '--accent': accentFor(s.value) }"
        >
          <div class="tile__label label">{{ s.icon }} {{ $t(s.labelKey) }}</div>
          <div class="tile__value display">{{ s.value }}<span class="tile__max mono">/100</span></div>
          <div class="tile__bar"><div class="tile__fill" :style="{ width: s.value + '%' }"></div></div>
        </div>
      </div>

      <!-- nearby places -->
      <section class="loc__places">
        <h2 class="loc__places-head display">{{ $t('location.nearby') }}</h2>
        <div class="loc__grid">
          <div v-for="g in groups" :key="g.key" class="grp">
            <div class="grp__head label">{{ g.icon }} {{ $t(g.labelKey) }}</div>
            <ul class="grp__list">
              <li v-for="item in g.items" :key="item.id" class="grp__row">
                <span class="grp__name">{{ item.name }}</span>
                <span class="grp__dist mono">{{ $t('location.walk', { dist: item.distance, min: walkMin(item.distance) }) }}</span>
              </li>
            </ul>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.loc {
  padding: 28px 32px 56px;
  max-width: 1100px;
}
.loc__title {
  font-size: 44px;
  line-height: 0.9;
  margin: 0;
}
.loc__sub {
  color: #555;
  margin-top: 8px;
}

/* input bar */
.loc__bar {
  display: flex;
  gap: 12px;
  margin-top: 24px;
}
.loc__input {
  flex: 1;
  border: var(--stroke);
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 14px 16px;
  font-size: 15px;
}
.loc__input:focus {
  outline: none;
  background: #fffdf5;
}
.loc__go {
  border: var(--stroke);
  background: var(--pink);
  color: #fff;
  padding: 0 26px;
  box-shadow: var(--shadow);
  cursor: pointer;
  white-space: nowrap;
  transition: transform 0.08s ease;
}
.loc__go:active {
  transform: translate(2px, 2px);
  box-shadow: 2px 2px 0 0 var(--ink);
}
.loc__go:disabled {
  background: var(--neutral);
  cursor: default;
}
.loc__hint {
  color: #777;
  margin-top: 10px;
  font-size: 11px;
}
.loc__example {
  border: none;
  background: none;
  color: var(--pink);
  cursor: pointer;
  font: inherit;
  padding: 0 0 0 6px;
  text-transform: uppercase;
}

.loc__error {
  margin-top: 18px;
  border: var(--stroke);
  border-left: 6px solid var(--pink);
  background: #fff;
  padding: 12px 14px;
  color: var(--ink);
}
.loc__loading {
  margin-top: 20px;
  color: #555;
}

/* overall */
.loc__overall {
  margin-top: 28px;
  border: var(--stroke-thick);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
  padding: 18px 22px;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-areas: 'meta num' 'bar bar';
  align-items: center;
  gap: 8px 16px;
}
.loc__overall-meta {
  grid-area: meta;
}
.loc__overall-label {
  color: #555;
}
.loc__overall-grade {
  font-size: 20px;
  color: var(--accent);
  margin-top: 2px;
}
.loc__overall-num {
  grid-area: num;
  font-size: 72px;
  line-height: 0.8;
  color: var(--accent);
}
.loc__overall-bar {
  grid-area: bar;
  height: 14px;
  border: var(--stroke);
  background: var(--bg);
  margin-top: 6px;
}
.loc__overall-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.4s ease;
}

/* sub-score tiles */
.loc__tiles {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
}
.tile {
  border: var(--stroke);
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 14px;
  border-top: 6px solid var(--accent);
}
.tile__label {
  color: #555;
  font-size: 11px;
}
.tile__value {
  margin-top: 8px;
  font-size: 40px;
  line-height: 1;
}
.tile__max {
  font-size: 13px;
  color: #999;
  margin-left: 3px;
}
.tile__bar {
  height: 8px;
  border: var(--stroke);
  background: var(--bg);
  margin-top: 10px;
}
.tile__fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.4s ease;
}

/* nearby */
.loc__places {
  margin-top: 36px;
}
.loc__places-head {
  font-size: 24px;
  margin: 0 0 14px;
}
.loc__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}
.grp {
  border: var(--stroke);
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 14px 16px;
}
.grp__head {
  border-bottom: var(--stroke);
  padding-bottom: 8px;
  margin-bottom: 6px;
  font-size: 14px;
}
.grp__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.grp__row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #cfcabb;
  font-size: 15px;
}
.grp__row:last-child {
  border-bottom: none;
}
.grp__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.grp__dist {
  color: #4a4a4a;
  font-size: 13px;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .loc { padding: 16px 14px 48px; }
  .loc__title { font-size: 32px; }
  .loc__bar { flex-direction: column; }
  .loc__go { padding: 13px; }
  .loc__overall { padding: 14px 16px; }
  .loc__overall-num { font-size: 52px; }
}
</style>
