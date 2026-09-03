<script setup>
/* Ego ownership-network for a single entity. Loaded on /e/<key>/network */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { goBack } from '../router'
import { useAuthStore } from '../stores/authStore'
import OwnershipGraph from '../components/OwnershipGraph.vue'
import GraphLegend from '../components/GraphLegend.vue'
import DisclaimerBanner from '../components/DisclaimerBanner.vue'
import { setPageMeta } from '../lib/pageMeta'
import { useIsMobile } from '../lib/useIsMobile'

const props = defineProps({ ekey: String })
const { t } = useI18n()
const auth = useAuthStore()
const isMobile = useIsMobile()

const name = ref('')
const net = ref({ nodes: [], edges: [], center: null })
const depth = ref(2)
const loading = ref(true)
const error = ref(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    name.value = (await api.entity(props.ekey)).name
    setPageMeta({
      title: t('meta.entityNetworkTitle', { name: name.value }),
      description: t('meta.entityNetworkDesc', { name: name.value }),
    })
    // The network endpoint is login-gated (401 for anonymous) — only fetch it when
    // signed in; otherwise the template shows the lock CTA.
    if (auth.isAuthenticated) net.value = await api.entityNetwork(props.ekey, depth.value)
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}
async function reloadNetwork() {
  if (auth.isAuthenticated) net.value = await api.entityNetwork(props.ekey, depth.value)
}

const winHeight = ref(window.innerHeight)
function onResize() { winHeight.value = window.innerHeight }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))
// Mobile loses height to the fixed header + the wrapped (two-row) topbar.
const graphHeight = computed(() => winHeight.value - (isMobile.value ? 170 : 60))

watch(() => props.ekey, load, { immediate: true })
watch(depth, reloadNetwork)
watch(() => auth.isAuthenticated, load) // sign in/out reveals/hides the network
</script>

<template>
  <div class="page">
    <header class="topbar">
      <button class="ghost" @click="goBack(`/e/${ekey}`)">← {{ name || $t('entity.profile') }}</button>
      <div class="mono tag">{{ $t('entity.networkTag') }}</div>
      <div class="toolbar">
        <span class="label">{{ $t('entity.depth') }}</span>
        <div class="seg">
          <button v-for="d in [1, 2, 3]" :key="d" :class="{ on: depth === d }" @click="depth = d">{{ d }}</button>
        </div>
        <span class="mono count">{{ $t('entity.nodesLinks', { nodes: net.nodes.length, links: net.edges.length }) }}</span>
      </div>
    </header>

    <div v-if="error" class="banner">{{ error }}</div>
    <div v-else-if="loading" class="loading display">{{ $t('entity.loading') }}</div>

    <div v-else-if="!auth.isAuthenticated" class="lockwrap">
      <div class="lockpanel">
        <div class="display lockbig">🔒</div>
        <h2 class="display">{{ $t('entity.networkLocked') }}</h2>
        <p class="lockmsg">{{ name ? $t('entity.networkLockedMsgNamed', { name }) : $t('entity.networkLockedMsg') }}</p>
        <button class="lockbtn" @click="auth.openModal()">{{ $t('common.signInUnlock') }}</button>
      </div>
    </div>

    <div v-else class="canvas">
      <OwnershipGraph :nodes="net.nodes" :edges="net.edges" :center-id="net.center" :height="graphHeight" />
      <DisclaimerBanner overlay />
      <div class="legend-wrap"><GraphLegend /></div>
    </div>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.topbar {
  display: flex; align-items: center; gap: 16px; flex: none;
  padding: 10px 24px; border-bottom: var(--stroke-thick); background: var(--surface);
}
.tag { font-size: 11px; color: #555; }
.toolbar { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.seg { display: inline-flex; border: var(--stroke); box-shadow: var(--shadow); }
.seg button { border: none; border-right: var(--stroke); background: var(--surface); padding: 5px 13px; font-weight: 800; font-family: var(--font-display); cursor: pointer; }
.seg button:last-child { border-right: none; }
.seg button.on { background: var(--pink); color: #fff; }
.count { font-size: 12px; color: #555; }
.ghost {
  border: var(--stroke); background: var(--surface); box-shadow: var(--shadow);
  padding: 6px 12px; font-weight: 700; cursor: pointer; white-space: nowrap;
}
.ghost:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.banner { margin: 16px 24px; border: var(--stroke); background: var(--pink); color: #fff; padding: 10px; }
.canvas { position: relative; flex: 1; min-height: 0; }
.legend-wrap { position: absolute; right: 14px; bottom: 14px; }
.loading { padding: 60px; font-size: 24px; }
.lockwrap { flex: 1; display: flex; align-items: center; justify-content: center; }
.lockpanel { text-align: center; max-width: 340px; padding: 28px; border: var(--stroke); background: var(--surface); box-shadow: var(--shadow-lg); }
.lockbig { font-size: 52px; line-height: 1; }
.lockpanel h2 { font-size: 26px; margin: 8px 0; }
.lockmsg { font-size: 13px; color: #555; margin: 8px 0 14px; line-height: 1.45; }
.lockbtn {
  border: var(--stroke); background: var(--pink); color: #fff; box-shadow: var(--shadow);
  padding: 10px 16px; font-weight: 800; font-family: var(--font-display); text-transform: uppercase; cursor: pointer;
}
.lockbtn:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }

@media (max-width: 768px) {
  .page {
    height: calc(100vh - var(--mhead-h)); /* fallback for browsers without dvh */
    height: calc(100dvh - var(--mhead-h));
  }
  .topbar { flex-wrap: wrap; gap: 8px; padding: 10px 12px; }
  .toolbar { margin-left: 0; width: 100%; }
  .legend-wrap { right: 8px; bottom: 8px; transform: scale(0.9); transform-origin: bottom right; }
}
</style>
