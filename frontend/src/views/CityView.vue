<script setup>
// One city's neighbourhood bubble field. One bubble per neighbourhood; the active
// metric (price / buy-signal) drives size + colour. Bubbles are arranged by their
// real geography (lat/lon) so neighbours sit in their true compass direction.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '../stores/appStore'
import { isExtended } from '../lib/scope'
import { AIR_METRICS } from '../lib/metrics'
import AppLink from '../components/AppLink.vue'
import Navbar from '../components/Navbar.vue'
import BubbleCluster from '../components/BubbleCluster.vue'
import PtrInfoPanel from '../components/PtrInfoPanel.vue'
import { useIsMobile } from '../lib/useIsMobile'
import { setPageMeta } from '../lib/pageMeta'

const props = defineProps({ city: { type: String, required: true } })
const { t } = useI18n()

// Phones show the same geo field zoomed out (small bubbles, everything visible);
// pinch/buttons zoom in to read names — labels un-truncate as you zoom.
const isMobile = useIsMobile()

const store = useAppStore()
// (Re)load whenever the route's city changes.
watch(() => props.city, (c) => c && store.loadCity(c), { immediate: true })
// In air mode, surface how the air data was collected so values read as
// indicative (citizen sensors, sampled), not regulatory-grade.
const isAir = computed(() => AIR_METRICS.includes(store.metric))

watch([() => store.cityName, isAir], ([name, air]) => {
  if (name) setPageMeta({
    title: air ? `${name} · ${t('nav.airQuality')}` : name,
    description: t('meta.cityDesc', { name }),
  })
}, { immediate: true })

const cluster = ref(null)

// City-scoped deep-link prefix so a bubble click stays within this city.
const linkPrefix = computed(() => `/c/${props.city}/n`)
// Back to this section's country map.
const backTo = computed(() => (isAir.value ? '/air-quality' : '/'))

const nodes = computed(() => {
  const m = store.metricDef
  // store.scopedFeatures already drops villages/towns when the active city is
  // Sofia and scope === 'sofia'.
  return store.scopedFeatures.map((f) => ({
    slug: f.slug,
    name: f.name,
    lat: f.lat,
    lon: f.lon,
    value: m.size(f),
    // Out-of-city bubbles read as secondary regardless of metric.
    color: isExtended(f.slug) ? 'var(--village)' : m.color(f),
    label: m.valueText(f),
  }))
})
</script>

<template>
  <div class="field">
    <Navbar />
    <div v-if="isAir" class="field__warn mono">⚠ {{ $t('season.airNote') }}</div>
    <main class="field__canvas">
      <BubbleCluster
        ref="cluster"
        :nodes="nodes"
        mode="pack"
        :radius-range="isMobile ? [10, 26] : null"
        :link-prefix="linkPrefix"
      />
      <PtrInfoPanel v-if="store.metric === 'ptr'" />
      <AppLink :to="backTo" class="field__back label">{{ $t('city.back') }}</AppLink>
      <div class="field__zoom">
        <button class="field__zbtn" :title="$t('city.zoomIn')" @click="cluster?.zoomIn()">+</button>
        <button class="field__zbtn" :title="$t('city.zoomOut')" @click="cluster?.zoomOut()">−</button>
        <button class="field__zbtn" :title="$t('city.resetView')" @click="cluster?.resetZoom()">⟲</button>
      </div>
      <div class="field__note mono">{{ $t(store.metricDef.legendKey) }}</div>
      <div v-if="store.loading" class="field__status label">{{ $t('city.loadingMarket') }}</div>
      <div v-else-if="store.error" class="field__status field__status--err label">
        {{ store.error }}
      </div>
    </main>
  </div>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.field__canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  background: var(--bg);
  overflow: hidden;
}
/* Air-mode data disclaimer: a slim strip under the navbar so it's always read,
   never overlapping the bubble-field controls. Soft warning yellow, black stroke. */
.field__warn {
  flex: none;
  background: #FBE9A0;
  border-bottom: var(--stroke);
  padding: 6px 16px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--ink);
}
.field__back {
  position: absolute;
  left: 16px;
  top: 16px;
  z-index: 500;
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  padding: 8px 12px;
  cursor: pointer;
}
.field__back:active {
  transform: translate(2px, 2px);
  box-shadow: 2px 2px 0 0 var(--ink);
}
.field__note {
  position: absolute;
  left: 16px;
  bottom: 14px;
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  padding: 6px 10px;
  font-size: 11px;
  color: #555;
  max-width: 320px;
}
.field__status {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 500;
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  padding: 8px 16px;
}
.field__status--err { background: var(--pink); color: #fff; }
.field__zoom {
  position: absolute;
  right: 16px;
  bottom: 14px;
  z-index: 500;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field__zbtn {
  width: 38px;
  height: 38px;
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  font-family: var(--font-display);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.field__zbtn:active {
  transform: translate(2px, 2px);
  box-shadow: 2px 2px 0 0 var(--ink);
}

/* Mobile: same fixed-height field as desktop (below the app header), so touch
   pan/pinch belongs entirely to the bubble canvas — no page scroll to fight. */
@media (max-width: 768px) {
  .field {
    height: calc(100vh - var(--mhead-h)); /* fallback for browsers without dvh */
    height: calc(100dvh - var(--mhead-h));
  }
  .field__back {
    left: 12px;
    top: 12px;
    padding: 7px 10px;
  }
  .field__note {
    left: 12px;
    bottom: 12px;
    font-size: 10px;
    max-width: 56%;
  }
  .field__zoom {
    right: 12px;
    bottom: 12px;
  }
}
</style>
