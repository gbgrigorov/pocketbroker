<script setup>
defineProps({
  label: String,
  value: String,
  accent: { type: String, default: 'var(--coral)' },
})
</script>

<template>
  <div class="tile" :style="{ '--accent': accent }">
    <div class="tile__label label">{{ label }}</div>
    <div class="tile__value mono">{{ value }}</div>
  </div>
</template>

<style scoped>
.tile {
  border: var(--stroke);
  background: var(--surface);
  box-shadow: var(--shadow);
  padding: 12px;
  border-top: 6px solid var(--accent);
}
.tile__label {
  color: #555;
  font-size: 10px;
}
.tile__value {
  margin-top: 6px;
  font-family: var(--font-display);
  font-weight: 800;
  font-size: 26px;
  line-height: 1;
}
</style>
