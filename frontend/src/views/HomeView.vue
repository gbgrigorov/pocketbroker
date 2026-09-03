<script setup>
// Landing page: the country map. Pick a city to open its neighbourhood field.
import { onMounted } from 'vue'
import { useAppStore } from '../stores/appStore'
import BulgariaMap from '../components/BulgariaMap.vue'
import { resetPageMeta } from '../lib/pageMeta'

const store = useAppStore()
onMounted(() => {
  store.city = null // we're at country level — no active city
  store.loadCities()
  resetPageMeta()
})
</script>

<template>
  <div class="home">
    <header class="home__head">
      <h1 class="home__title display">{{ $t('home.title') }}</h1>
      <p class="home__sub label">{{ $t('home.subtitle') }}</p>
    </header>

    <main class="home__canvas">
      <BulgariaMap :cities="store.cities" />
      <div v-if="store.loading" class="home__status label">{{ $t('home.loadingCities') }}</div>
      <div v-else-if="store.error" class="home__status home__status--err label">
        {{ store.error }}
      </div>
    </main>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
}
.home__head {
  border-bottom: var(--stroke);
  background: var(--surface);
  padding: 18px 28px;
}
.home__title {
  font-size: 44px;
  line-height: 0.9;
  text-transform: uppercase;
}
.home__sub {
  margin-top: 6px;
  color: #555;
}
.home__canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 28px;
  overflow: auto;
}
.home__status {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  padding: 8px 16px;
}
.home__status--err { background: var(--pink); color: #fff; }

@media (max-width: 768px) {
  .home {
    height: auto;
    min-height: calc(100vh - var(--mhead-h)); /* fallback for browsers without dvh */
    min-height: calc(100dvh - var(--mhead-h));
  }
  .home__head { padding: 14px 16px; }
  .home__title { font-size: 32px; }
  .home__canvas {
    align-items: flex-start;
    padding: 16px 12px;
  }
}
</style>
