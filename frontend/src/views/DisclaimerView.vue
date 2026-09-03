<script setup>
/* Data & AI Disclaimer. Body copy lives in the i18n catalog (legal.disclaimer.body). */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import LegalPage from '../components/LegalPage.vue'
import { setPageMeta } from '../lib/pageMeta'

const { t } = useI18n()
onMounted(() => setPageMeta({ title: t('meta.disclaimerTitle'), description: t('meta.disclaimerDesc') }))
</script>

<template>
  <LegalPage :title="$t('legal.disclaimer.heading')" :updated="$t('legal.updatedDate')">
    <div v-html="$t('legal.disclaimer.body')"></div>
  </LegalPage>
</template>
