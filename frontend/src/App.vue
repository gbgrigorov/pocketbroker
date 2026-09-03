<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, navigate } from './router'
import { useAppStore } from './stores/appStore'
import { useAuthStore } from './stores/authStore'
import AppLink from './components/AppLink.vue'
import Sidebar from './components/Sidebar.vue'
import AuthModal from './components/AuthModal.vue'
import HomeView from './views/HomeView.vue'
import CityView from './views/CityView.vue'
import NeighbourhoodView from './views/NeighbourhoodView.vue'
import EntitiesView from './views/EntitiesView.vue'
import EntityView from './views/EntityView.vue'
import EntityNetworkView from './views/EntityNetworkView.vue'
import CertificateView from './views/CertificateView.vue'
import EntityReportView from './views/EntityReportView.vue'
import AdminView from './views/AdminView.vue'
import LocationView from './views/LocationView.vue'
import AboutView from './views/AboutView.vue'
import TermsView from './views/TermsView.vue'
import PrivacyView from './views/PrivacyView.vue'
import DisclaimerView from './views/DisclaimerView.vue'
import ConsentBanner from './components/ConsentBanner.vue'
import { useConsentStore, trackPageview } from './stores/consentStore'

const route = useRoute()
const store = useAppStore()
const auth = useAuthStore()
const consent = useConsentStore()

// Mobile nav drawer. Any navigation closes it (sidebar buttons mutate the route).
const menuOpen = ref(false)
// Route changes are GA pageviews too — fires after the new view (and its <title>)
// has rendered, via nextTick inside trackPageview's caller below.
// The URL is the source of truth for which section we're in (real estate vs air
// quality); keep the active metric in step with it. Immediate so a cold deep-link
// to /air-quality/* sets the air metric before the first render (pre-flush watcher).
watch(route, () => {
  store.applySection(route.value.section)
  menuOpen.value = false
  nextTick(() => trackPageview())
}, { immediate: true })
watch(menuOpen, (open) => document.body.classList.toggle('no-scroll', open))

onMounted(async () => {
  // Returning visitor who already accepted analytics — load GA without re-prompting.
  if (consent.analytics) consent.enableAnalytics()
  if (consent.analytics) nextTick(() => trackPageview())

  // Google OAuth bounces back to /auth?token=… (the router's legacy-hash redirect
  // has already converted #/auth?token=… to this path by the time we get here) —
  // capture it, then clean the URL.
  const m = (window.location.pathname + window.location.search).match(/^\/auth\?token=([^&]+)/)
  if (m) {
    auth.setToken(decodeURIComponent(m[1]))
    await auth.fetchMe()
    navigate('/entities')
  } else {
    auth.fetchMe() // rehydrate an existing session on normal load
  }
})
</script>

<template>
  <div class="shell" :class="{ 'shell--bare': route.name === 'certificate' }">
    <header v-if="route.name !== 'certificate'" class="mhead">
      <button
        class="mhead__burger"
        :class="{ 'mhead__burger--open': menuOpen }"
        :aria-expanded="menuOpen"
        :aria-label="$t('common.menu')"
        @click="menuOpen = !menuOpen"
      >
        <span></span><span></span><span></span>
      </button>
      <AppLink to="/" class="mhead__logo display">BG INTEL</AppLink>
    </header>
    <Sidebar v-if="route.name !== 'certificate'" class="shell__sidebar" :class="{ 'shell__sidebar--open': menuOpen }" />
    <div
      class="shell__scrim"
      :class="{ 'shell__scrim--show': menuOpen }"
      @click="menuOpen = false"
    ></div>
    <main class="shell__view">
      <HomeView v-if="route.name === 'home'" />
      <CityView v-else-if="route.name === 'city'" :key="route.city" :city="route.city" />
      <EntitiesView v-else-if="route.name === 'entities'" />
      <EntityView v-else-if="route.name === 'entity'" :key="route.key" :ekey="route.key" />
      <EntityNetworkView v-else-if="route.name === 'entity-network'" :key="route.key + '-net'" :ekey="route.key" />
      <CertificateView v-else-if="route.name === 'certificate'" :key="route.key + '-cert'" :ekey="route.key" />
      <EntityReportView v-else-if="route.name === 'entity-report'" :key="route.key + '-rep'" :ekey="route.key" :slug="route.slug" />
      <AdminView v-else-if="route.name === 'admin'" />
      <LocationView v-else-if="route.name === 'location'" />
      <AboutView v-else-if="route.name === 'about'" />
      <TermsView v-else-if="route.name === 'terms'" />
      <PrivacyView v-else-if="route.name === 'privacy'" />
      <DisclaimerView v-else-if="route.name === 'disclaimer'" />
      <NeighbourhoodView v-else :slug="route.slug" :city="route.city" :key="route.city + '/' + route.slug" />
    </main>
    <AuthModal v-if="auth.modalOpen" />
    <ConsentBanner />
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;
  height: 100vh;
}
/* Certificate route reads as a standalone document — no sidebar/header chrome. */
.shell--bare {
  grid-template-columns: 1fr;
}
.shell--bare .shell__view {
  grid-column: 1;
}
.shell__sidebar {
  grid-column: 1;
}
.shell__view {
  grid-column: 2;
  min-width: 0;
  height: 100vh;
  overflow-y: auto;
}
.mhead,
.shell__scrim {
  display: none;
}

/* ── Mobile: fixed header + off-canvas sidebar drawer (screen only) ─────────── */
@media screen and (max-width: 768px) {
  .shell {
    display: block;
    height: auto;
  }
  .shell__view {
    height: auto;
    min-height: 100vh; /* fallback for browsers without dvh */
    min-height: 100dvh;
    overflow: visible;
    padding-top: var(--mhead-h);
  }
  .shell--bare .shell__view { padding-top: 0; }
  .mhead {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 800;
    height: var(--mhead-h);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 12px;
    background: var(--surface);
    border-bottom: var(--stroke);
  }
  .mhead__burger {
    flex: none;
    width: 42px;
    height: 42px;
    padding: 0;
    background: var(--surface);
    border: var(--stroke);
    box-shadow: 3px 3px 0 0 var(--ink);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 5px;
    cursor: pointer;
  }
  .mhead__burger:active {
    transform: translate(2px, 2px);
    box-shadow: 1px 1px 0 0 var(--ink);
  }
  .mhead__burger span {
    width: 20px;
    height: 3px;
    background: var(--ink);
    transition: transform 0.2s ease, opacity 0.15s ease;
  }
  .mhead__burger--open span:nth-child(1) { transform: translateY(8px) rotate(45deg); }
  .mhead__burger--open span:nth-child(2) { opacity: 0; }
  .mhead__burger--open span:nth-child(3) { transform: translateY(-8px) rotate(-45deg); }
  .mhead__logo {
    font-size: 20px;
    line-height: 1;
    background: var(--ink);
    color: var(--bg);
    padding: 4px 9px;
    cursor: pointer;
  }
  /* Drawer slides in under the header, so the burger stays reachable as a close
     toggle. Extra 12px in the hidden offset keeps the hard shadow off-screen. */
  .shell__sidebar {
    position: fixed;
    top: var(--mhead-h);
    bottom: 0;
    left: 0;
    z-index: 790;
    width: min(80vw, 300px);
    transform: translateX(calc(-100% - 12px));
    transition: transform 0.22s ease;
    box-shadow: var(--shadow-lg);
  }
  .shell__sidebar--open {
    transform: none;
  }
  .shell__scrim {
    display: block;
    position: fixed;
    inset: var(--mhead-h) 0 0 0;
    z-index: 780;
    background: rgba(13, 13, 13, 0.45);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s ease;
  }
  .shell__scrim--show {
    opacity: 1;
    pointer-events: auto;
  }
}

/* Print: the shell is a fixed-height (100vh) scroll container, which forces the
   certificate onto extra pages. Let it flow naturally so the sheet is one page. */
@media print {
  .shell,
  .shell__view {
    display: block;
    height: auto;
    min-height: 0;
    overflow: visible;
  }
}
</style>
