<script setup>
// Home bubble-field top strip: bubble-size metric selector + year slider.
import { computed, watch } from 'vue'
import { useAppStore } from '../stores/appStore'
import { METRICS, METRIC_ORDER, AIR_METRICS } from '../lib/metrics'

const store = useAppStore()
const PRICE_MIN = 1995
const PRICE_MAX = 2026
// The metric strip is contextual: in air mode it shows AQI/PM2.5 (+ the
// winter/summer toggle); otherwise the price/buy metrics. Keeps the bar uncrowded.
const isAir = computed(() => AIR_METRICS.includes(store.metric))
const metrics = computed(() => {
  const fam = isAir.value ? AIR_METRICS : METRIC_ORDER.filter((k) => !AIR_METRICS.includes(k))
  return fam.map((k) => METRICS[k])
})

// Slider bounds are contextual. Prices span a fixed 1995–2026; air spans exactly
// the years we have for the active season (derived from the data via the store),
// so the rail never offers a year with no air — winter 2018–2026, summer 2017–2025.
const airSeasonYears = computed(() => store.airYears[store.season] || [])
const MIN = computed(() =>
  isAir.value && airSeasonYears.value.length ? airSeasonYears.value[0] : PRICE_MIN
)
const MAX = computed(() =>
  isAir.value && airSeasonYears.value.length
    ? airSeasonYears.value[airSeasonYears.value.length - 1]
    : PRICE_MAX
)

// Keep the selected year inside the active range. Switching into air mode (or
// toggling season) can leave `year` outside the new bounds — e.g. on 2026 winter
// then switching to summer, which only has data through 2025 — so clamp it.
watch([isAir, () => store.season, MIN, MAX], () => {
  if (store.year == null) return
  if (store.year > MAX.value) store.setYear(MAX.value)
  else if (store.year < MIN.value) store.setYear(MIN.value)
})

// Live year: every drag tick commits to the store so the bubbles morph as you
// slide, letting you watch the market move year-by-year. All years are cached
// client-side (see appStore), so this is pure local re-derivation — no refetch.
const sliderYear = computed({
  get: () => store.year ?? MAX.value,
  set: (v) => store.setYear(Number(v)),
})
const isLatest = computed(() => store.year === null)
// Label for the "latest" thumb position: prices read "2026·now"; air reads the
// newest year actually available for the season (e.g. 2025 for summer).
const latestLabel = computed(() => (isAir.value ? String(MAX.value) : '2026·now'))
</script>

<template>
  <header class="nav">
    <div class="nav__left">
      <div class="nav__chips">
        <span
          v-for="m in metrics"
          :key="m.key"
          class="nav__chip label"
          :class="{ 'nav__chip--active': store.metric === m.key }"
          @click="store.setMetric(m.key)"
        >{{ $t(m.labelKey) }}</span>
      </div>

      <div v-if="store.city === 'sofia' && !isAir" class="nav__chips nav__scope">
        <span
          class="nav__chip label"
          :class="{ 'nav__chip--active': store.scope === 'sofia' }"
          @click="store.setScope('sofia')"
        >{{ $t('city.sofia') }}</span>
        <span
          class="nav__chip label"
          :class="{ 'nav__chip--active': store.scope === 'extended' }"
          @click="store.setScope('extended')"
        >{{ $t('city.sofiaExtended') }}</span>
      </div>

      <div v-if="isAir" class="nav__chips nav__season">
        <span
          class="nav__chip label"
          :class="{ 'nav__chip--winter': store.season === 'winter' }"
          @click="store.setSeason('winter')"
        >{{ $t('season.winter') }}</span>
        <span
          class="nav__chip label"
          :class="{ 'nav__chip--summer': store.season === 'summer' }"
          @click="store.setSeason('summer')"
        >{{ $t('season.summer') }}</span>
      </div>
    </div>

    <div class="nav__year">
      <button class="nav__latest label" :class="{ 'nav__latest--on': isLatest }" @click="store.setYear(null)">
        {{ $t('city.latest') }}
      </button>
      <span class="nav__yval mono">{{ store.year ?? latestLabel }}</span>
      <input
        class="nav__slider"
        type="range"
        :min="MIN"
        :max="MAX"
        :value="sliderYear"
        @input="sliderYear = $event.target.value"
      />
      <span class="nav__bounds mono">{{ MIN }}–{{ MAX }}</span>
    </div>
  </header>
</template>

<style scoped>
.nav {
  background: var(--surface);
  border-bottom: var(--stroke);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  gap: 20px;
  height: 64px;
}
.nav__left {
  display: flex;
  align-items: center;
  gap: 20px;
}
.nav__chips {
  display: flex;
  gap: 8px;
}
.nav__scope .nav__chip--active {
  background: var(--ink);
  color: var(--bg);
}
.nav__season {
  padding-left: 10px;
  border-left: var(--stroke);
}
.nav__chip {
  border: var(--stroke);
  padding: 6px 12px;
  background: var(--surface);
  box-shadow: 3px 3px 0 0 var(--ink);
  cursor: pointer;
}
.nav__chip:active {
  transform: translate(2px, 2px);
  box-shadow: 1px 1px 0 0 var(--ink);
}
.nav__chip--active {
  background: var(--pink);
  color: #fff;
}
/* Winter/summer active state: black fill, white text. Declared after the base
   .nav__chip rule so its background wins (equal specificity → source order). */
.nav__chip--winter,
.nav__chip--summer {
  background: var(--ink);
  color: #fff;
}
.nav__year {
  display: flex;
  align-items: center;
  gap: 12px;
}
.nav__latest {
  border: var(--stroke);
  background: var(--surface);
  padding: 6px 12px;
}
.nav__latest--on {
  background: var(--ink);
  color: var(--bg);
}
.nav__yval {
  min-width: 76px;
  text-align: center;
  font-weight: 500;
  font-size: 15px;
  border: var(--stroke);
  padding: 5px 8px;
  background: var(--coral);
  color: #fff;
}
.nav__slider {
  width: 220px;
  accent-color: var(--pink);
}
.nav__bounds {
  font-size: 11px;
  color: #777;
}

/* Mobile: two slim rows — ALL chips (metric + scope, divider between) share one
   horizontally swipeable rail; the year slider stretches across the second row. */
@media (max-width: 768px) {
  .nav {
    height: auto;
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
    padding: 8px 10px 10px;
  }
  .nav__left {
    align-items: center;
    gap: 10px;
    overflow-x: auto;
    scrollbar-width: none;
    /* breathing room so the chips' hard shadows aren't clipped by the scroll box */
    padding: 2px 2px 5px;
  }
  .nav__left::-webkit-scrollbar {
    display: none;
  }
  .nav__chips {
    flex: none;
    gap: 8px;
  }
  .nav__scope {
    padding-left: 10px;
    border-left: var(--stroke);
  }
  .nav__chip {
    flex: none;
    white-space: nowrap;
    padding: 7px 11px;
  }
  .nav__year {
    gap: 10px;
  }
  .nav__latest {
    padding: 6px 10px;
  }
  .nav__slider {
    flex: 1;
    width: auto;
    min-width: 0;
  }
  .nav__bounds {
    display: none;
  }
}
</style>
