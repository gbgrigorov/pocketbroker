<script setup>
// Flat Neo-Memphis map of Bulgaria: a thick-stroked country silhouette with one
// clickable pin per city. The outline and the pins share one projection
// (lib/bulgaria-geo), so each pin — placed from its city's centroid — lands
// inside the border. Label cards are HTML overlaid on the SVG and positioned by
// percentage of the viewBox, so they get real CSS borders/shadows/fonts.
import { computed } from 'vue'
import { navigate, cityPath } from '../router'
import { useAppStore } from '../stores/appStore'
import { AIR_METRICS } from '../lib/metrics'
import { OUTLINE_PATH, VIEW_BOX, VIEW_W, VIEW_H, project } from '../lib/bulgaria-geo'

const props = defineProps({
  cities: { type: Array, default: () => [] }, // [{ slug, name, lat, lon, neighbourhood_count, avg_eur_sqm, air }]
})

const store = useAppStore()
const isAir = computed(() => AIR_METRICS.includes(store.metric))

// The pin number follows the active metric: price (€/m²) in the default flow,
// or the city's seasonal air value (AQI / PM2.5) in air mode.
function pinValue(c) {
  if (!isAir.value) {
    return c.avg_eur_sqm != null ? '€' + Math.round(c.avg_eur_sqm) + '/m²' : '—'
  }
  const a = c.air?.[store.season]
  if (!a) return '—'
  return store.metric === 'aqi'
    ? (a.aqi != null ? 'AQI ' + a.aqi : '—')
    : (a.pm25 != null ? a.pm25 + ' µg/m³' : '—')
}

// Pins with their screen position (% of the viewBox) + which side the label card
// sits on, so coastal cities (far east) don't push their card off-canvas.
const pins = computed(() =>
  props.cities
    .filter((c) => c.lat != null && c.lon != null)
    .map((c) => {
      const { x, y } = project(c.lon, c.lat)
      return {
        slug: c.slug,
        name: c.name,
        avg: pinValue(c),
        count: c.neighbourhood_count,
        xPct: (x / VIEW_W) * 100,
        yPct: (y / VIEW_H) * 100,
        side: x > VIEW_W * 0.6 ? 'left' : 'right',
      }
    }),
)

function open(slug) {
  // Drill into the matching section's city page (air country map → air city).
  navigate(cityPath(slug, isAir.value ? 'air' : 'estate'))
}
</script>

<template>
  <div class="map" :style="{ aspectRatio: `${VIEW_W} / ${VIEW_H}` }">
    <svg class="map__svg" :viewBox="VIEW_BOX" preserveAspectRatio="xMidYMid meet">
      <path :d="OUTLINE_PATH" class="map__outline" />
    </svg>

    <button
      v-for="p in pins"
      :key="p.slug"
      class="pin"
      :class="`pin--${p.side}`"
      :style="{ left: p.xPct + '%', top: p.yPct + '%' }"
      @click="open(p.slug)"
    >
      <span class="pin__dot" aria-hidden="true"></span>
      <span class="pin__card">
        <span class="pin__name display">{{ p.name }}</span>
        <span class="pin__avg mono">{{ p.avg }}</span>
        <span class="pin__count label">{{ p.count }} areas</span>
      </span>
    </button>
  </div>
</template>

<style scoped>
.map {
  position: relative;
  width: 100%;
  max-width: 920px;
  margin: 0 auto;
}
.map__svg {
  display: block;
  width: 100%;
  height: 100%;
}
.map__outline {
  fill: var(--surface);
  stroke: var(--ink);
  stroke-width: 4;
  stroke-linejoin: round;
}

/* A pin = an anchor dot at the centroid + a label card beside it. The button is
   zero-size at the centroid; children are positioned relative to it. */
.pin {
  position: absolute;
  width: 0;
  height: 0;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
}
.pin__dot {
  position: absolute;
  left: 0;
  top: 0;
  width: 16px;
  height: 16px;
  transform: translate(-50%, -50%);
  background: var(--pink);
  border: var(--stroke);
  border-radius: 50%;
  box-shadow: 2px 2px 0 0 var(--ink);
}
.pin__card {
  position: absolute;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 10px;
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  white-space: nowrap;
  transition: transform 0.08s ease, box-shadow 0.08s ease;
}
/* Card sits to the right of the dot by default, to the left for coastal cities. */
.pin--right .pin__card { left: 14px; transform: translateY(-50%); }
.pin--left .pin__card { right: 14px; transform: translateY(-50%); }
.pin:hover .pin__card {
  box-shadow: var(--shadow-lg);
}
.pin--right:hover .pin__card { transform: translateY(-50%) translate(-2px, -2px); }
.pin--left:hover .pin__card { transform: translateY(-50%) translate(2px, -2px); }
.pin:active .pin__card { box-shadow: 2px 2px 0 0 var(--ink); }

.pin__name {
  font-size: 20px;
  line-height: 1;
  text-transform: uppercase;
}
.pin__avg {
  font-size: 13px;
  color: var(--pink);
  font-weight: 500;
}
.pin__count {
  font-size: 10px;
  color: #777;
}

/* Mobile: smaller dots + label cards so coastal pins stay inside the canvas. */
@media (max-width: 768px) {
  .pin__dot {
    width: 12px;
    height: 12px;
  }
  .pin__card {
    padding: 4px 7px;
    box-shadow: 3px 3px 0 0 var(--ink);
  }
  .pin--right .pin__card { left: 10px; }
  .pin--left .pin__card { right: 10px; }
  .pin__name { font-size: 14px; }
  .pin__avg { font-size: 11px; }
  .pin__count { font-size: 9px; }
}
</style>
