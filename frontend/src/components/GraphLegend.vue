<script setup>
// Colour key for the ownership graph — matches OwnershipGraph node/edge styling.
</script>

<template>
  <div class="legend">
    <div class="legend__row"><span class="dot builder"></span> {{ $t('graphLegend.builder') }}</div>
    <div class="legend__row"><span class="dot company"></span> {{ $t('graphLegend.company') }}</div>
    <div class="legend__row"><span class="dot person"></span> {{ $t('graphLegend.person') }}</div>
    <div class="legend__row"><span class="dot warn"></span> {{ $t('graphLegend.withSignal') }}</div>
    <div class="legend__row"><span class="line own"></span> {{ $t('graphLegend.ownership') }}</div>
    <div class="legend__row"><span class="line mgmt"></span> {{ $t('graphLegend.management') }}</div>
    <div class="legend__row"><span class="line hist"></span> {{ $t('graphLegend.historical') }}</div>
  </div>
</template>

<style scoped>
.legend {
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  padding: 10px 12px;
  display: grid;
  gap: 6px;
  font-family: var(--font-head);
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.legend__row { display: flex; align-items: center; gap: 8px; }
.dot { width: 13px; height: 13px; border: 2px solid var(--ink); border-radius: 50%; flex: none; }
.dot.builder { background: var(--pink); }
.dot.company { background: var(--blue); }
.dot.person { background: var(--coral); }
.dot.warn { background: #FFD400; }
.line { width: 20px; height: 0; flex: none; }
.line.own { border-top: 3px solid var(--teal); }
.line.mgmt { border-top: 3px solid #8a8a8a; }
.line.hist { border-top: 3px dashed #8a8a8a; }
</style>
