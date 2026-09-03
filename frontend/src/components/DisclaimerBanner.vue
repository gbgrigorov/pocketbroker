<script setup>
/* Compact warning banner: this site only surfaces public-record links between
 * companies/people and any court cases — it does not investigate or draw
 * conclusions, and the data is AI-collected so errors are possible.
 * `overlay` floats it over a fixed-height canvas (e.g. the network graph)
 * instead of taking up layout space. */
import { ref } from 'vue'

defineProps({ overlay: { type: Boolean, default: false } })

const dismissed = ref(false)
</script>

<template>
  <div v-if="!dismissed" class="disclaimer" :class="{ 'disclaimer--overlay': overlay }">
    <span class="disclaimer__icon">⚠</span>
    <p v-html="$t('disclaimerBanner.body')"></p>
    <button class="disclaimer__close" @click="dismissed = true" :aria-label="$t('disclaimerBanner.dismiss')">×</button>
  </div>
</template>

<style scoped>
.disclaimer {
  display: flex; align-items: flex-start; gap: 10px;
  background: #FFF8EC; border: var(--stroke); border-left: 6px solid #b22;
  box-shadow: var(--shadow); padding: 10px 14px; margin: 0 0 16px;
}
.disclaimer__icon { font-size: 16px; line-height: 1.5; flex: none; }
.disclaimer p { flex: 1; margin: 0; font-size: 12.5px; line-height: 1.5; color: #333; }
.disclaimer p :deep(a) { color: var(--pink); font-weight: 700; }
.disclaimer__close {
  flex: none; border: none; background: none; cursor: pointer;
  font-size: 18px; line-height: 1; color: #999; padding: 0 2px;
}
.disclaimer__close:hover { color: #333; }

.disclaimer--overlay {
  position: absolute; top: 10px; left: 14px; right: 14px; z-index: 5;
  max-width: 640px;
}

@media (max-width: 768px) {
  .disclaimer { padding: 8px 10px; }
  .disclaimer p { font-size: 11.5px; }
  .disclaimer--overlay { left: 8px; right: 8px; top: 8px; max-width: none; }
}
</style>
