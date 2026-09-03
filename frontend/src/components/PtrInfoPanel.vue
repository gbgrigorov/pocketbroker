<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { PTR_TONE_COLOR } from '../lib/finance'

const { t } = useI18n()

const STORAGE_KEY = 'ptr-info-v1'
const dismissed = ref(false)

onMounted(() => {
  if (localStorage.getItem(STORAGE_KEY)) dismissed.value = true
})

function close() {
  localStorage.setItem(STORAGE_KEY, '1')
  dismissed.value = true
}

const SCALE = [
  { value: '15',   color: PTR_TONE_COLOR.good,      labelKey: 'city.ptrInfo.scale.v15label',  subKey: 'city.ptrInfo.scale.v15sub' },
  { value: '17.5', color: PTR_TONE_COLOR.fair,      labelKey: 'city.ptrInfo.scale.v175label', subKey: 'city.ptrInfo.scale.v175sub' },
  { value: '20',   color: PTR_TONE_COLOR.stretched, labelKey: 'city.ptrInfo.scale.v20label',  subKey: 'city.ptrInfo.scale.v20sub' },
  { value: '25',   color: PTR_TONE_COLOR.expensive, labelKey: 'city.ptrInfo.scale.v25label',  subKey: 'city.ptrInfo.scale.v25sub' },
]
</script>

<template>
  <div v-if="!dismissed" class="ptr-info">
    <div class="ptr-info__head">
      <span class="ptr-info__title mono">P / R RATIO</span>
      <button class="ptr-info__close" @click="close" :aria-label="t('city.ptrInfo.dismiss')">×</button>
    </div>
    <p class="ptr-info__body">{{ t('city.ptrInfo.body') }}</p>
    <div class="ptr-info__scale">
      <div v-for="item in SCALE" :key="item.value" class="ptr-info__chip">
        <span class="ptr-info__dot" :style="{ background: item.color }"></span>
        <span class="ptr-info__text">
          <span class="ptr-info__num">{{ item.value }}</span>
          <span class="ptr-info__label">{{ t(item.labelKey) }}</span>
          <span class="ptr-info__sub">{{ t(item.subKey) }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ptr-info {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 500;
  width: 272px;
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  padding: 12px 14px 14px;
}

.ptr-info__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 7px;
}

.ptr-info__title {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: #555;
  text-transform: uppercase;
}

.ptr-info__close {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  color: #aaa;
  padding: 0 2px;
  flex: none;
}
.ptr-info__close:hover { color: var(--ink); }

.ptr-info__body {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.5;
  color: #444;
}

.ptr-info__scale {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 6px;
}

.ptr-info__chip {
  display: flex;
  align-items: flex-start;
  gap: 7px;
}

.ptr-info__dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 1.5px solid rgba(0, 0, 0, 0.25);
  flex: none;
  margin-top: 3px;
}

.ptr-info__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.ptr-info__num {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 700;
  line-height: 1;
  color: var(--ink);
}

.ptr-info__label {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.3;
  margin-top: 1px;
}

.ptr-info__sub {
  font-size: 9.5px;
  color: #888;
  line-height: 1.3;
  margin-top: 1px;
}

@media (max-width: 768px) {
  .ptr-info {
    top: 12px;
    right: 12px;
    width: 240px;
    padding: 10px 12px 12px;
  }
  .ptr-info__body { font-size: 11.5px; }
}
</style>
