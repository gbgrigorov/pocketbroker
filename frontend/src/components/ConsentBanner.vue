<script setup>
/* Bottom cookie/analytics consent banner. Shown until the visitor makes a choice.
 * Accept loads Google Analytics; Decline keeps it off. Neo-Memphis styling. */
import { useConsentStore } from '../stores/consentStore'

const consent = useConsentStore()
</script>

<template>
  <div v-if="!consent.decided" class="cb" role="dialog" :aria-label="$t('consent.title')">
    <div class="cb__text">
      <strong class="cb__title display">{{ $t('consent.title') }}</strong>
      <p v-html="$t('consent.body')"></p>
    </div>
    <div class="cb__actions">
      <button class="cb__btn cb__btn--ghost label" @click="consent.decline()">{{ $t('consent.decline') }}</button>
      <button class="cb__btn cb__btn--accept label" @click="consent.accept()">{{ $t('consent.accept') }}</button>
    </div>
  </div>
</template>

<style scoped>
.cb {
  position: fixed; z-index: 1100; left: 16px; right: 16px; bottom: 16px;
  max-width: 760px; margin: 0 auto;
  background: var(--surface); border: var(--stroke-thick); box-shadow: var(--shadow-lg);
  padding: 16px 18px;
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
}
.cb__text { flex: 1; min-width: 240px; }
.cb__title { display: block; font-size: 16px; margin-bottom: 4px; }
.cb__text p { margin: 0; font-size: 13px; line-height: 1.5; color: #333; }
.cb__text a { color: var(--pink); font-weight: 700; }

.cb__actions { display: flex; gap: 10px; flex: none; }
.cb__btn {
  border: var(--stroke); box-shadow: var(--shadow); padding: 10px 16px;
  font-weight: 800; cursor: pointer; transition: transform 0.08s ease;
}
.cb__btn:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.cb__btn--ghost { background: var(--surface); color: var(--ink); }
.cb__btn--accept { background: var(--pink); color: #fff; }

@media (max-width: 560px) {
  .cb__actions { width: 100%; }
  .cb__btn { flex: 1; }
}
</style>
