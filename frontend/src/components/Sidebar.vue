<script setup>
// Global navigation — persistent on every page. Below the nav, a metric-aware
// neighbourhood ranking (shown on the price-context routes).
import { computed } from 'vue'
import { useAppStore } from '../stores/appStore'
import { useAuthStore } from '../stores/authStore'
import { useRoute, cityPath } from '../router'
import AppLink from './AppLink.vue'
import LangSwitcher from './LangSwitcher.vue'

const store = useAppStore()
const auth = useAuthStore()
const route = useRoute()

// Real estate and air quality are two parallel sections, each with its own URL.
// Keep the active city when switching sections (so /c/sofia ⇄ /air-quality/sofia),
// else point at that section's country map.
const onMap = computed(() => route.value.name === 'home' || route.value.name === 'city')
const fieldTo = computed(() => cityPath(store.city, 'estate'))
const airTo = computed(() => cityPath(store.city, 'air'))
const onEstateMap = computed(() => onMap.value && route.value.section !== 'air')
const onAirMap = computed(() => onMap.value && route.value.section === 'air')

const onEntities = computed(() => route.value.name === 'entities' || route.value.name === 'entity')
const onLocation = computed(() => route.value.name === 'location')
const onAbout = computed(() => route.value.name === 'about')
const onAdmin = computed(() => route.value.name === 'admin')
const showRanks = computed(() => route.value.name === 'city' || route.value.name === 'neighbourhood')
// Deep-link prefix for ranking rows — stays within the active city.
const rankPrefix = computed(() => (store.city ? `/c/${store.city}/n` : '/n'))
</script>

<template>
  <aside class="sb">
    <div class="sb__brand">
      <div class="sb__logo display">BG INTEL</div>
      <div class="sb__tag label">{{ $t('brand.analytics', { name: store.cityName || $t('brand.bulgaria') }) }}</div>
    </div>

    <nav class="sb__nav">
      <AppLink :to="fieldTo" class="sb__item label" :class="{ 'sb__item--active': onEstateMap }">
        {{ $t('nav.bubbleField') }}
      </AppLink>

      <AppLink :to="airTo" class="sb__item label" :class="{ 'sb__item--active': onAirMap }">
        {{ $t('nav.airQuality') }}
      </AppLink>

      <AppLink to="/entities" class="sb__item label" :class="{ 'sb__item--active': onEntities }">
        {{ $t('nav.builders') }}
      </AppLink>
      <AppLink to="/location" class="sb__item label" :class="{ 'sb__item--active': onLocation }">
        {{ $t('nav.locationScore') }}
      </AppLink>
      <AppLink to="/about" class="sb__item label" :class="{ 'sb__item--active': onAbout }">
        {{ $t('nav.howItWorks') }}
      </AppLink>
      <AppLink
        v-if="auth.user?.is_superuser"
        to="/admin"
        class="sb__item sb__item--admin label"
        :class="{ 'sb__item--active': onAdmin }"
      >
        {{ $t('nav.admin') }}
      </AppLink>
    </nav>

    <div v-if="showRanks && store.ranked.length" class="sb__rank">
      <div class="sb__rank-head label">{{ $t(store.metricDef.rankLabelKey) }}</div>
      <ol class="sb__list">
        <li v-for="(f, i) in store.ranked.slice(0, 6)" :key="f.slug">
          <AppLink
            :to="`${rankPrefix}/${f.slug}`"
            class="sb__rankrow"
            :class="{ 'sb__rankrow--active': f.slug === store.activeSlug }"
          >
            <span class="sb__rk mono">{{ i + 1 }}</span>
            <span class="sb__rn">{{ f.name }}</span>
            <span class="sb__rv mono">{{ f.text }}</span>
          </AppLink>
        </li>
      </ol>
    </div>

    <div class="sb__foot">
      <div v-if="auth.isAuthenticated" class="sb__user">
        <div class="sb__who">
          <span class="sb__avatar">{{ (auth.displayName[0] || '?').toUpperCase() }}</span>
          <span class="sb__name" :title="auth.displayName">{{ auth.displayName }}</span>
        </div>
        <button class="sb__logout label" @click="auth.logout()">{{ $t('nav.logout') }}</button>
      </div>
      <button v-else class="sb__signin label" @click="auth.openModal()">{{ $t('nav.signIn') }}</button>

      <LangSwitcher />

      <nav class="sb__legal">
        <AppLink to="/terms">{{ $t('nav.terms') }}</AppLink>
        <span aria-hidden="true">·</span>
        <AppLink to="/privacy">{{ $t('nav.privacy') }}</AppLink>
        <span aria-hidden="true">·</span>
        <AppLink to="/disclaimer">{{ $t('nav.disclaimer') }}</AppLink>
      </nav>
    </div>
  </aside>
</template>

<style scoped>
.sb {
  background: var(--surface);
  border-right: var(--stroke);
  padding: 18px 16px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  height: 100%;
  overflow-y: auto;
}
.sb__logo {
  font-size: 30px;
  line-height: 0.95;
  background: var(--ink);
  color: var(--bg);
  padding: 6px 10px;
  display: inline-block;
}
.sb__tag {
  margin-top: 8px;
  color: #555;
}
.sb__nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sb__item {
  text-align: left;
  background: var(--surface);
  border: var(--stroke);
  padding: 10px 12px;
  box-shadow: var(--shadow);
  transition: transform 0.08s ease;
  cursor: pointer;
  color: var(--ink);
  text-decoration: none;
}
.sb__item:active {
  transform: translate(2px, 2px);
  box-shadow: 2px 2px 0 0 var(--ink);
}
.sb__item--active {
  background: var(--pink);
  color: #fff;
}
.sb__item--admin:not(.sb__item--active) {
  border-left: 6px solid var(--teal);
}
.sb__rank-head {
  margin-bottom: 10px;
  color: #555;
}
.sb__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sb__rankrow {
  display: grid;
  grid-template-columns: 20px 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border: var(--stroke);
  font-size: 13px;
  cursor: pointer;
  color: var(--ink);
  text-decoration: none;
}
.sb__rankrow:hover {
  background: var(--bg);
}
.sb__rankrow--active {
  background: var(--teal);
}
.sb__rk {
  font-weight: 600;
}
.sb__rn {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sb__rv {
  font-size: 12px;
}
.sb__foot {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sb__signin {
  background: var(--pink);
  color: #fff;
  border: var(--stroke);
  padding: 11px;
  box-shadow: var(--shadow);
  cursor: pointer;
  font-weight: 800;
  text-transform: uppercase;
}
.sb__signin:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.sb__user {
  border: var(--stroke);
  box-shadow: var(--shadow);
  background: var(--surface);
  padding: 9px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.sb__who { display: flex; align-items: center; gap: 8px; min-width: 0; }
.sb__avatar {
  flex: none; width: 26px; height: 26px; border: var(--stroke);
  background: var(--teal); display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--font-display); font-weight: 800; font-size: 14px;
}
.sb__name { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sb__logout {
  flex: none; border: var(--stroke); background: var(--surface); padding: 5px 8px;
  font-size: 11px; cursor: pointer;
}
.sb__logout:active { transform: translate(1px, 1px); }
.sb__legal {
  display: flex; flex-wrap: wrap; gap: 5px; justify-content: center;
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: #999;
  padding-top: 2px;
}
.sb__legal a { color: #777; text-decoration: none; }
.sb__legal a:hover { color: var(--pink); }

/* Mobile drawer: the fixed header already shows the wordmark, so drop the brand
   block and give touch rows a little more height. */
@media (max-width: 768px) {
  .sb__brand { display: none; }
  .sb { gap: 18px; padding-bottom: max(18px, env(safe-area-inset-bottom)); }
  .sb__item { padding: 13px 14px; }
  .sb__rankrow { padding: 10px 8px; }
}
</style>
