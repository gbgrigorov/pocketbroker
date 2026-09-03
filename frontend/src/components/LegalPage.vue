<script setup>
/* Shared shell for the legal pages (Terms / Privacy / Disclaimer). Renders the
 * Neo-Memphis page chrome (title, last-updated, cross-links). The three content
 * views stay copy-only and pass their body through the default slot. */
import AppLink from './AppLink.vue'

defineProps({
  title: { type: String, required: true },
  updated: { type: String, default: '' },
})
</script>

<template>
  <div class="legal">
    <header class="head">
      <div class="mono tag">{{ $t('legal.tag') }}</div>
      <h1 class="display title">{{ title }}</h1>
      <p v-if="updated" class="mono updated">{{ $t('legal.updatedLabel', { date: updated }) }}</p>
    </header>

    <div class="body">
      <slot />
    </div>

    <footer class="foot mono">
      <span>{{ $t('legal.footer') }}</span>
      <span class="links">
        <AppLink to="/terms">{{ $t('legal.footTerms') }}</AppLink> ·
        <AppLink to="/privacy">{{ $t('legal.footPrivacy') }}</AppLink> ·
        <AppLink to="/disclaimer">{{ $t('legal.footDisclaimer') }}</AppLink>
      </span>
    </footer>
  </div>
</template>

<style scoped>
.legal { max-width: 820px; margin: 0 auto; padding: 32px 28px 72px; }

.head { margin-bottom: 28px; }
.tag { font-size: 11px; color: #555; }
.title { font-size: 44px; line-height: 0.95; margin: 10px 0 6px; }
.updated { font-size: 11px; color: #777; }

/* Content typography — applies to whatever the slot renders. */
.body :deep(h2) {
  font-family: var(--font-display); font-weight: 800; text-transform: uppercase;
  font-size: 22px; letter-spacing: 0.02em;
  border-bottom: var(--stroke); padding-bottom: 6px; margin: 36px 0 14px;
}
.body :deep(h3) { font-family: var(--font-head); font-weight: 700; font-size: 16px; margin: 22px 0 8px; }
.body :deep(p) { font-size: 15px; line-height: 1.6; margin: 0 0 14px; }
.body :deep(ul) { margin: 0 0 16px; padding-left: 20px; }
.body :deep(li) { font-size: 15px; line-height: 1.55; margin-bottom: 8px; }
.body :deep(a) { color: var(--pink); font-weight: 600; }
.body :deep(strong) { font-weight: 700; }
.body :deep(.card) {
  background: var(--surface); border: var(--stroke); box-shadow: var(--shadow);
  padding: 16px 18px; margin: 0 0 18px;
}
.body :deep(.warn) {
  background: #FFF8EC; border: var(--stroke); border-left: 6px solid #b22;
  box-shadow: var(--shadow); padding: 16px 18px; margin: 0 0 18px;
}
.body :deep(.muted) { color: #777; font-size: 13px; }

.foot {
  margin-top: 48px; padding-top: 16px; border-top: var(--stroke);
  font-size: 11px; color: #777; display: flex; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
}
.foot .links a { color: #555; }
</style>
