<script setup>
/* Privacy Policy (GDPR). Body copy lives in the i18n catalog (legal.privacy.body). */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import LegalPage from '../components/LegalPage.vue'
import { setPageMeta } from '../lib/pageMeta'

const { t } = useI18n()
onMounted(() => setPageMeta({ title: t('meta.privacyTitle'), description: t('meta.privacyDesc') }))
</script>

<template>
  <LegalPage :title="$t('legal.privacy.heading')" :updated="$t('legal.updatedDate')">
    <div v-html="$t('legal.privacy.body')"></div>
  </LegalPage>
</template>
