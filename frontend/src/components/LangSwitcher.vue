<script setup>
// BG | EN language toggle. Switches the UI-chrome locale (DB data stays Cyrillic).
import { useI18n } from 'vue-i18n'
import { setLocale } from '../i18n'

const { locale } = useI18n()
</script>

<template>
  <div class="lang" role="group" :aria-label="$t('lang.label')">
    <button
      class="lang__btn label"
      :class="{ 'lang__btn--on': locale === 'bg' }"
      :aria-pressed="locale === 'bg'"
      @click="setLocale('bg')"
    >{{ $t('lang.bg') }}</button>
    <button
      class="lang__btn label"
      :class="{ 'lang__btn--on': locale === 'en' }"
      :aria-pressed="locale === 'en'"
      @click="setLocale('en')"
    >{{ $t('lang.en') }}</button>
  </div>
</template>

<style scoped>
.lang {
  display: inline-flex;
  border: var(--stroke);
  box-shadow: var(--shadow);
  align-self: flex-start;
}
.lang__btn {
  border: none;
  border-right: var(--stroke);
  background: var(--surface);
  padding: 6px 14px;
  font-weight: 800;
  cursor: pointer;
}
.lang__btn:last-child { border-right: none; }
.lang__btn--on { background: var(--pink); color: #fff; }
.lang__btn:active { transform: translate(1px, 1px); }
</style>
