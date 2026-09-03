<script setup>
/* Terms of Service. Body copy lives in the i18n catalog (legal.terms.body). */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import LegalPage from '../components/LegalPage.vue'
import { setPageMeta } from '../lib/pageMeta'

const { t } = useI18n()
onMounted(() => setPageMeta({ title: t('meta.termsTitle'), description: t('meta.termsDesc') }))
</script>

<template>
  <LegalPage :title="$t('legal.terms.heading')" :updated="$t('legal.updatedDate')">
    <div v-html="$t('legal.terms.body')"></div>
  </LegalPage>
</template>
